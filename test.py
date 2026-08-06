import news_module as nm
count = nm.fetch_and_store_news("台股")
print(f"本次新增了 {count} 筆新聞")
