from smolagents import WebSearchTool
import requests
from bs4 import BeautifulSoup
import re

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
        # Try to get the main content, fallback to all text
        main = soup.find('main')
        if main:
            text = main.get_text(separator=' ', strip=True)
        else:
            text = soup.get_text(separator=' ', strip=True)
        # Limit to first 2000 characters for brevity
        return text[:2000]
    except requests.exceptions.HTTPError as e:
        if response.status_code == 500 and retry:
            # Retry once
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
    # Regex to match: [Title](URL)\nSnippet\n
    pattern = re.compile(r'\[(.*?)\]\((https?://[^\)]+)\)\n(.*?)(?=\n\[|\n*$)', re.DOTALL)
    matches = pattern.findall(output)
    results = []
    for title, url, snippet in matches:
        results.append({'title': title.strip(), 'url': url.strip(), 'snippet': snippet.strip()})
    return results


def main():
    book_query = input("Enter a Book name or ISBN: ")
    search_tool = WebSearchTool()
    try:
        output = search_tool(book_query)
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
    # Try to get 3 successful scrapes, using more URLs if needed
    successful_results = []
    used_indices = set()
    idx = 0
    while len(successful_results) < 3 and idx < len(parsed_results):
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
    if len(successful_results) < 3:
        print(f"Only {len(successful_results)} successful scrapes found.")
    save_structured_results(successful_results)


if __name__ == "__main__":
    main()