from scrape import search_amazon_books
import subprocess
import os
from rich.console import Console

console = Console()

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
            return
        selected_path = selected_image.stdout.decode('utf-8').strip().split("||")[1]
        selected_index = image_paths.index(selected_path)
        # Display the selected image and its metadata
        os.system(f"kitty icat '{image_paths[selected_index]}'")
        console.print(image_metadata[selected_index], style="bold blue")
    except Exception:
        console.print(selected_image.stderr.decode('utf-8'), style="bold red")
        console.print("No image selected. Exiting...", style="bold red")

if __name__ == "__main__":
    query = input("Enter a Book name or ISBN: ")
    results = search_amazon_books(query)
    fzf_preview(results) 