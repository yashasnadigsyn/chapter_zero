# cli.py

# --- Existing imports ---
from scrape import search_amazon_books
import subprocess
import os
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from smolagents import WebSearchTool
import requests
from bs4 import BeautifulSoup
import re
# --- New imports ---
import google.generativeai as genai
import pathlib
import time

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
        return text[:3500] # Slightly more context
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
        console.print(f"\n[bold green]✔[/bold green] Web research saved to [cyan]{filename}[/cyan]")
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
    if not results:
        console.print("No books found on Amazon for that query.", style="bold yellow")
        return None
    image_paths = [book['cover_image'] or '' for book in results]
    image_metadata = [f"{book['title'] or '<No Title>'}  |  {book['author'] or '<No Author>'}  |  {book['rating'] or '<No Rating>'}" for book in results]
    fzf_input = '\n'.join([f"{metadata}          ||{path}" for metadata, path in zip(image_metadata, image_paths)]).encode('utf-8')
    fzf_cmd = [
        'fzf', '--cycle', '--preview-window', 'noborder:right:60%', '--padding', '2',
        '--prompt', 'Select a book > ', '--marker', '>', '--pointer', '◆', '--reverse',
        '--info', 'right',
        '--preview', 'kitty icat --clear --transfer-mode=memory --stdin=no --place=${FZF_PREVIEW_COLUMNS}x${FZF_PREVIEW_LINES}@0x0  "$(echo {} | sed "s/.*||//")"',
        '--delimiter', '||',
    ]
    try:
        selected_image = subprocess.run(fzf_cmd, input=fzf_input, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        if not selected_image.stdout:
            console.print("No book selected. Exiting...", style="bold red")
            return None
        selected_path = selected_image.stdout.decode('utf-8').strip().split("||")[1]
        selected_index = image_paths.index(selected_path)
        console.print("\n[bold]You selected:[/bold]")
        console.print(image_metadata[selected_index], style="bold blue")
        return results[selected_index]
    except (subprocess.CalledProcessError, FileNotFoundError):
        console.print("[bold red]Error:[/bold red] `fzf` or `kitty` command failed. Please ensure they are installed and in your PATH.", style="bold red")
        console.print("Falling back to a simple list selection.", style="yellow")
        for i, book in enumerate(results[:10]):
            console.print(f"{i+1}. {book['title']} by {book.get('author', 'N/A')}")
        try:
            choice = int(input("Enter the number of the book you want: ")) - 1
            if 0 <= choice < len(results[:10]):
                return results[choice]
        except (ValueError, IndexError):
            pass
        console.print("Invalid selection. Exiting.", style="bold red")
        return None
    except Exception as e:
        console.print(f"An unexpected error occurred with fzf: {e}", style="bold red")
        return None

SYSTEM_PROMPT_V3 = """
You are "Chapter Zero," a deeply insightful and proactive AI book mentor. Your personality is that of a wise, friendly, and extremely curious guide. Your goal is to go beyond surface-level questions and truly help the user explore if a book is right for them by being an active research partner.

YOUR CORE DIRECTIVES:

1.  **ANALYZE & CONNECT:** Read the initial research file. Your first questions MUST be specific and show you've connected details from the research to the user's potential experience.
    *   **Bad:** "What's your background?"
    *   **Good:** "I saw in the table of contents that this book covers Bayesian statistics in Chapter 2. Is that a topic you're already comfortable with, or is that part of what you're hoping to learn?"

2.  **BE A PROACTIVE RESEARCHER (CRITICAL!):** Don't just wait for the user to reveal a knowledge gap. Be curious on their behalf. If the user's situation is common or sparks a question in your "mind," use your `search_the_web` tool to find anecdotal evidence or deeper context.
    *   **Your Trigger:** The user says something like, "I've never read any fantasy before," "I'm a beginner programmer," or "I found this book too slow."
    *   **Your Action:** This is your cue to think, "I wonder what other people in this situation think." Then, use the tool.
    *   **Excellent Proactive Search Example:** A user wants to read *The Lord of the Rings* but says, "I've never read Tolkien before." You should immediately think, "This is a common concern," and use your tool to search for something like: `"reddit experience reading Lord of the Rings without reading The Hobbit first"`.

3.  **CITE YOUR SOURCES:** When you use information, whether from the initial file or a new search, reference where it came from. This builds trust and allows the user to explore further.
    *   **Example (Initial File):** "According to the summary from `wikipedia.org` in the research file..."
    *   **Example (New Search):** "That's a great question. I just did a quick search and found a discussion on `stackexchange.com` that says..."

4.  **MAINTAIN A MENTOR'S TONE:** Be warm, encouraging, and conversational. Use phrases like "That's a great question," "That makes sense," "Let's dig into that." Guide the user to their own conclusion.

5. Keep your search terms shorter else searchtool won't work.
"""

def start_chat_with_chapter_zero(selected_book, search_results_path):
    """Initializes and runs the conversational loop with the proactive Chapter Zero AI."""
    
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        console.print("[bold red]ERROR:[/bold red] GOOGLE_API_KEY environment variable not set.")
        return

    genai.configure(api_key=api_key)
    web_search_tool = WebSearchTool()
    
    def search_the_web(query: str):
        """
        Searches the web for information about a specific query. Use this proactively to find community discussions (e.g., on Reddit, Stack Exchange) or deeper details about a book's content when the user's situation prompts curiosity.
        """
        console.print(Panel(f"[italic yellow]Chapter Zero is looking into:[/italic yellow] [bold]{query}[/bold]", border_style="yellow", expand=False))
        return web_search_tool(query)

    try:
        book_title = selected_book.get('title', 'Unknown Title')
        book_author = selected_book.get('author', 'Unknown Author')
        search_content = pathlib.Path(search_results_path).read_text(encoding='utf-8')

        initial_prompt = f"""
I'm thinking about reading "{book_title}" by {book_author}.

Here is the research I've gathered. Please analyze it and then start our conversation by following your core directives: ask a specific, grounded question and be ready to research proactively.

--- BEGIN SEARCH RESULTS ---
{search_content}
--- END SEARCH RESULTS ---
"""
        model = genai.GenerativeModel(
            model_name="gemini-2.5-flash",
            system_instruction=SYSTEM_PROMPT_V3,
            tools=[search_the_web]
        )
        chat = model.start_chat(enable_automatic_function_calling=True)

        console.print("\n[bold magenta]Connecting to Chapter Zero, your research partner...[/bold magenta]")
        
        with console.status("[bold yellow]Chapter Zero is analyzing the search...[/bold yellow]"):
            response = chat.send_message(initial_prompt)
        
        console.print("\n[bold magenta]Chapter Zero:[/bold magenta]")
        console.print(Markdown(response.text.strip()))

        while True:
            user_input = input("\n> You: ")
            if user_input.lower() in ["quit", "exit"]:
                console.print("\nHappy reading!", style="bold green")
                break
            
            if not user_input.strip():
                continue

            with console.status("[bold yellow]Chapter Zero is thinking...[/bold yellow]"):
                response = chat.send_message(user_input)
            
            console.print("\n[bold magenta]Chapter Zero:[/bold magenta]")
            console.print(Markdown(response.text.strip()))

    except Exception as e:
        console.print(f"\n[bold red]An error occurred during the chat session: {e}[/bold red]")

def main():
    query = input("Enter a Book name or ISBN: ")
    with console.status("[bold yellow]Searching Amazon...[/bold yellow]"):
        results = search_amazon_books(query)
    
    selected_book = fzf_preview(results)
    if not selected_book:
        return

    title = selected_book.get('title', '').strip()
    author = selected_book.get('author', '').strip()
    if not title:
        console.print("No title found for selected book. Exiting.", style="red")
        return

    search_query = title
    if author:
        search_query += f" by {author}"
    
    console.print(f"\n[bold]Conducting initial web research for:[/bold] [cyan]{search_query}[/cyan]")
    search_tool = WebSearchTool()
    
    try:
        with console.status("[bold yellow]Searching the web for context...[/bold yellow]"):
            output = search_tool(f"reviews, summary, and table of contents for the book {search_query}")
    except Exception as e:
        console.print(f"[ERROR during web search: {e}]", style="bold red")
        return

    if not output or not isinstance(output, str):
        console.print("No search results found or unexpected result format.", style="red")
        return
    
    parsed_results = parse_websearch_output(output)
    if not parsed_results:
        console.print("No valid URLs found in search results.", style="red")
        return

    successful_results = []
    idx = 0
    console.print("[bold]Scraping top results for analysis:[/bold]")
    # CHANGE 2: Verbose scraping loop
    while len(successful_results) < 4 and idx < len(parsed_results):
        r = parsed_results[idx]
        console.print(f"  [dim]-> Scraping {r['url']}...[/dim]")
        content = scrape_text_from_url(r['url'])
        if not content.startswith('[ERROR scraping'):
            r['content'] = content
            successful_results.append(r)
        time.sleep(0.2) # Small delay to make UX feel smoother
        idx += 1
    
    if not successful_results:
        console.print("Could not scrape any web pages for context. Unable to proceed.", style="bold red")
        return

    search_results_filename = "search_results.txt"
    save_structured_results(successful_results, search_results_filename)

    start_chat_with_chapter_zero(selected_book, search_results_filename)

if __name__ == "__main__":
    main()