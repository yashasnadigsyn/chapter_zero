from smolagents import WebSearchTool

book_query = input("Enter a Book name or ISBN: ")

search_prompt = f"Find comprehensive information about the book '{book_query}'. Include its table of contents, book summary, author details, related content, and reviews from Reddit or Twitter if available. Look at amazon reviews too and give me a summary of the reviews."

search_tool = WebSearchTool()
results = search_tool(search_prompt)
print(results)