import scrapy
from scrapy.crawler import CrawlerProcess
from scrapy.utils.project import get_project_settings
from scrapy import signals
from pydispatch import dispatcher

class AmazonBookSpider(scrapy.Spider):
    name = "amazon_books"
    allowed_domains = ["amazon.in"]

    def __init__(self, query=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.query = query or ""
        self.start_urls = [
            f"https://www.amazon.in/s?k={self.query.replace(' ', '+')}&s=books"
        ]
        self.results = []

    def parse(self, response):
        for book in response.css("div[data-component-type='s-search-result']"):
            title = book.css("h2 span::text").get()
            author = book.css(".a-row .a-size-base+ .a-link-normal::text, .a-row .a-size-base.a-link-normal::text").get()
            rating = book.css(".a-icon-alt::text").get()
            cover_image = book.css("img.s-image::attr(src)").get()
            self.results.append({
                "title": title,
                "author": author,
                "rating": rating,
                "cover_image": cover_image
            })

def search_amazon_books(query):
    settings = get_project_settings()
    settings.set('LOG_LEVEL', 'CRITICAL')
    process = CrawlerProcess(settings)
    results = {}
    def get_results(spider, reason):
        results['data'] = spider.results
    dispatcher.connect(get_results, signal=signals.spider_closed)
    process.crawl(AmazonBookSpider, query=query)
    process.start()
    return results.get('data', [])
