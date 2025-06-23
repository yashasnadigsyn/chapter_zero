from scrape import search_amazon_books
import subprocess
import os
from rich.console import Console
from smolagents import WebSearchTool
import requests
from bs4 import BeautifulSoup
import re

console = Console()

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)
HEADERS = {"User-Agent": USER_AGENT}

def scrape_text_from_url(url, retry=True):
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        main = soup.find('main')
        if main:
            text = main.get_text(separator=' ', strip=True)
        else:
            text = soup.get_text(separator=' ', strip=True)
        return text[:2000]
    except requests.exceptions.HTTPError as e:
        if response.status_code == 500 and retry:
            return scrape_text_from_url(url, retry=False)
        return f"[ERROR scraping {url}: {e}]"
    except Exception as e:
        return f"[ERROR scraping {url}: {e}]"

def save_structured_results(results, filename="search_results.txt"):
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            for result in results:
                f.write(f"URL: {result['url']}\n")
                f.write(f"TITLE: {result['title']}\n")
                f.write(f"CONTENTS:\n{result['content']}\n\n")
        print(f"Results saved to {filename}")
    except Exception as e:
        print(f"[ERROR saving results: {e}]")

def parse_websearch_output(output):
    pattern = re.compile(r'\[(.*?)\]\((https?://[^\)]+)\)\n(.*?)(?=\n\[|\n*$)', re.DOTALL)
    matches = pattern.findall(output)
    results = []
    for title, url, snippet in matches:
        results.append({'title': title.strip(), 'url': url.strip(), 'snippet': snippet.strip()})
    return results

def fzf_preview(results: list):
    """
        Preview the image using fzf and kitty icat
        Args:
            results (list): list of book dicts
        Returns:
            None
    """
    # Create a list of image URLs
    image_paths = [book['cover_image'] or '' for book in results]
    # Create a list of metadata strings
    image_metadata = [f"{book['title'] or '<No Title>'}  |  {book['author'] or '<No Author>'}  |  {book['rating'] or '<No Rating>'}" for book in results]
    # Create a list of strings containing the image metadata and the corresponding image path
    fzf_input = '\n'.join([f"{metadata}          ||{path}" for metadata, path in zip(image_metadata, image_paths)]).encode('utf-8')

    fzf_cmd = [
        'fzf',
        '--cycle',
        '--preview-window', 'noborder:right:60%',
        '--padding', '2',
        '--prompt', '> ',
        '--marker', '',
        '--pointer', '',
        '--separator', '',
        '--scrollbar', '',
        '--reverse',
        '--info', 'right',
        '--preview', 'kitty icat --clear --transfer-mode=memory --stdin=no --place=${FZF_PREVIEW_COLUMNS}x${FZF_PREVIEW_LINES}@0x0  "$(echo {} | sed "s/.*||//")"',
        '--delimiter', '||',
    ]
    try:
        selected_image = subprocess.run(fzf_cmd, input=fzf_input, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if not selected_image.stdout:
            console.print("No image selected. Exiting...", style="bold red")
            return None
        selected_path = selected_image.stdout.decode('utf-8').strip().split("||")[1]
        selected_index = image_paths.index(selected_path)
        # Display the selected image and its metadata
        os.system(f"kitty icat '{image_paths[selected_index]}'")
        console.print(image_metadata[selected_index], style="bold blue")
        return results[selected_index]
    except Exception:
        console.print(selected_image.stderr.decode('utf-8'), style="bold red")
        console.print("No image selected. Exiting...", style="bold red")
        return None

def main():
    query = input("Enter a Book name or ISBN: ")
    results = search_amazon_books(query)
    selected_book = fzf_preview(results)
    if not selected_book:
        return
    # Compose search query from title and author
    title = selected_book.get('title', '').strip()
    author = selected_book.get('author', '').strip()
    if not title:
        print("No title found for selected book. Exiting.")
        return
    search_query = title
    if author:
        search_query += f" {author}"
    print(f"\nSearching for: {search_query}\n")
    search_tool = WebSearchTool()
    try:
        output = search_tool(search_query)
    except Exception as e:
        print(f"[ERROR during web search: {e}]")
        return
    if not output or not isinstance(output, str):
        print("No search results found or unexpected result format.")
        return
    try:
        parsed_results = parse_websearch_output(output)
    except Exception as e:
        print(f"[ERROR parsing search results: {e}]")
        return
    if not parsed_results:
        print("No valid URLs found in search results.")
        return
    successful_results = []
    idx = 0
    while len(successful_results) < 5 and idx < len(parsed_results):
        r = parsed_results[idx]
        print(f"Scraping: {r['url']}")
        content = scrape_text_from_url(r['url'])
        if content.startswith('[ERROR scraping'):
            print(content)
            idx += 1
            continue
        r['content'] = content
        successful_results.append(r)
        idx += 1
    if len(successful_results) < 5:
        print(f"Only {len(successful_results)} successful scrapes found.")
    save_structured_results(successful_results)

if __name__ == "__main__":
    main() 