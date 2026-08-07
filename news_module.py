import feedparser
import sqlite3
import urllib.parse
import os
import re
import json
import time
import requests
from groq import Groq
import google.generativeai as genai
from email.utils import parsedate_to_datetime
import datetime

# 動態匯入 Google Gemini，未安裝時自動停用該備援，不影響系統運作
try:
    import google.generativeai as genai
    HAS_GEMINI_SDK = True
except ImportError:
    HAS_GEMINI_SDK = False

# 強制設定台灣台北時區 (UTC+8)
TZ_TAIPEI = datetime.timezone(datetime.timedelta(hours=8))

EXCLUDE_KEYWORDS = [
    "娛樂", "影劇", "星際", "星座", "八卦", "演唱會", "職棒", 
    "中職", "NBA", "電影", "網紅", "藝人", "電視劇", "綜藝",
    "定期定額", "小資族", "新手", "教學", "開戶", "ETF掛牌",
    "存股", "理財", "買房", "租屋", "信用卡", "現金回饋", "保險",
    "退休", "省錢", "發票", "中獎", "運勢", "生肖",
    "飼主", "寵物", "鄰居", "社會", "車禍", "命案", "外送", "勞基法"
]

CATALYST_TERMS = [
    "營收", "財報", "獲利", "毛利率", "單月EPS", "EPS", "轉虧為盈", "虧轉盈", 
    "大單", "訂單", "擴產", "庫存去化", "急單", "創高", "新高", "爆單", "停利",
    "重訊", "庫藏股", "併購", "減資", "增資", "現增", "配息", "殖利率", "除權息", 
    "申報轉讓", "法說會", "法說", "改選", "私募", "經營權", "買庫藏股", "CB", "公司債",
    "外資", "投信", "三大法人", "法人", "主力", "買超", "賣超", "借券", "官股",
    "漲停", "跌停", "漲停板", "跌停板", "鎖死", "處置股", "注意股", "全額交割",
    "半導體", "晶圓代工", "先進封裝", "CoWoS", "CPO", "矽光子", "水冷", "散熱", 
    "伺服器", "ASIC", "IP", "CCL", "PCB", "機器人", "算力", "晶片", "光通訊",
    "強韌電網", "重電", "變壓器", "儲能", "綠電", "風電", "軍工", "無人機", 
    "金管會", "央行", "升息", "降息", "禁令", "通膨", "Fed", "關稅", "制裁"
]

STOCKS_MAP = {
    "台積電": "台積電(2330)", "聯電": "聯電(2303)", "力積電": "力積電(6770)",
    "聯發科": "聯發科(2454)", "世芯": "世芯-KY(3661)", "創意": "創意(3443)",
    "鴻海": "鴻海(2317)", "廣達": "廣達(2382)", "緯創": "緯創(3231)", "緯穎": "緯穎(6669)",
    "奇鋐": "奇鋐(3017)", "雙鴻": "雙鴻(3324)", "健策": "健策(3653)", "台達電": "台達電(2308)",
    "華城": "華城(1519)", "士電": "士電(1503)", "中興電": "中興電(1513)", "亞力": "亞力(1514)",
    "雷虎": "雷虎(8033)", "漢翔": "漢翔(2634)", "所羅門": "所羅門(2359)", "昆盈": "昆盈(2365)",
    "長榮": "長榮(2603)", "陽明": "陽明(2609)", "萬海": "萬海(2615)",
    "富邦金": "富邦金(2881)", "國泰金": "國泰金(2882)", "中信金": "中信金(2891)"
}

def clean_old_news():
    try:
        conn = sqlite3.connect("news.db")
        cursor = conn.cursor()
        cutoff_date = (datetime.datetime.now(TZ_TAIPEI) - datetime.timedelta(days=3)).strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("DELETE FROM news WHERE published_date < ?", (cutoff_date,))
        conn.commit()
        conn.close()
    except Exception:
        pass

def clear_all_news():
    try:
        conn = sqlite3.connect("news.db")
        cursor = conn.cursor()
        cursor.execute("DELETE FROM news")
        conn.commit()
        conn.close()
        return True
    except Exception:
        return False

def init_db():
    conn = sqlite3.connect("news.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS news (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT UNIQUE,
            title TEXT,
            source TEXT,
            published_date TEXT,
            summary TEXT,
            importance TEXT,
            impact_companies TEXT,
            report_count INTEGER DEFAULT 1,
            is_ai INTEGER DEFAULT 1
        )
    """)
    conn.commit()
    conn.close()
    clean_old_news()

def parse_pub_date(published_str):
    try:
        dt = parsedate_to_datetime(published_str)
        dt_taipei = dt.astimezone(TZ_TAIPEI)
        return dt_taipei.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return datetime.datetime.now(TZ_TAIPEI).strftime("%Y-%m-%d %H:%M:%S")

def clean_title_for_comparison(title):
    cleaned = re.sub(r' - [^-]+$', '', title)
    cleaned = re.sub(r'^[【《\[\(][^】》\]\)]+[】》\]\)]', '', cleaned)
    cleaned = re.sub(r'^(快訊|注意|特報|即時|焦點|頭條|商情)[／/！!：:\-\s]*', '', cleaned)
    cleaned = re.sub(r'[^\u4e00-\u9fa5a-zA-Z0-9]', '', cleaned)
    return cleaned[:10]

def parse_ai_response(text):
    summary, importance, impact_companies = "", "⚪ 低", ""
    for line in text.split("\n"):
        if "摘要：" in line:
            summary = line.replace("摘要：", "").strip()
        elif "重要性：" in line:
            importance = line.replace("重要性：", "").strip()
        elif "影響台股：" in line:
            val = line.replace("影響台股：", "").strip()
            if val != "無":
                impact_companies = val
    return summary, importance, impact_companies, 1

def analyze_news_with_ai(title, source):
    """四重 AI 引擎自動接力備援"""
    prompt = f"""
    你是一個專業的台股操盤手。請評估以下新聞是否具備實質影響台股股價或產業預期的潛力：
    新聞標題：{title}
    新聞來源：{source}

    判斷標準：
    - 若屬於一般理財、生活消費、社會新聞、寵物、無具體公司財報/訂單的小道消息、或與台股無關，請將重要性設為「⚪ 低」。
    - 若屬於核心維度（政策紅利、突發風險、基本面拐點、總經變數、供應鏈衝擊），請將重要性設為「🔴 高」或「🟡 中」。

    請嚴格依照下列格式回傳：
    摘要：[用一句話精準說明事件本質與市場影響]
    重要性：[請填 🔴高、🟡中、或 ⚪低]
    影響台股：[必須明確列出受此事件影響的台股公司名稱與代號，例如：台積電(2330)。若無法明確對應具體台股代號或屬低價值新聞，請填「無」]
    """
    
    groq_key = os.environ.get("GROQ_API_KEY")
    gemini_key = os.environ.get("GEMINI_API_KEY")
    deepseek_key = os.environ.get("DEEPSEEK_API_KEY")

    # 1. Groq (70B)
    if groq_key:
        try:
            client = Groq(api_key=groq_key)
            response = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1
            )
            return parse_ai_response(response.choices[0].message.content.strip())
        except Exception:
            pass

    # 2. Google Gemini (1.5 Flash)
    if gemini_key and HAS_GEMINI_SDK:
        try:
            genai.configure(api_key=gemini_key)
            model = genai.GenerativeModel("gemini-1.5-flash")
            response = model.generate_content(prompt)
            return parse_ai_response(response.text.strip())
        except Exception:
            pass

    # 3. DeepSeek API
    if deepseek_key:
        try:
            headers = {
                "Authorization": f"Bearer {deepseek_key}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": "deepseek-chat",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.1
            }
            res = requests.post("https://api.deepseek.com/chat/completions", json=payload, headers=headers, timeout=10)
            if res.status_code == 200:
                content = res.json()['choices'][0]['message']['content']
                return parse_ai_response(content.strip())
        except Exception:
            pass

    # 4. Groq 輕量模型 (8B)
    if groq_key:
        try:
            client = Groq(api_key=groq_key)
            response = client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1
            )
            return parse_ai_response(response.choices[0].message.content.strip())
        except Exception:
            pass

    # 5. 純靜態規則庫降級備援
    return fallback_rule_analysis(title)

def fallback_rule_analysis(title):
    has_catalyst = any(term in title for term in CATALYST_TERMS)
    if not has_catalyst:
        return "", "⚪ 低", "", 0

    matched_stock = ""
    match_a = re.search(r'([\u4e00-\u9fa5\w\-]+)[\(（](\d{4})[\)）]', title)
    match_b = re.search(r'(\d{4})\s*([\u4e00-\u9fa5\w\-]+)', title)
    
    if match_a:
        matched_stock = f"{match_a.group(1)}({match_a.group(2)})"
    elif match_b and len(match_b.group(2)) >= 2:
        matched_stock = f"{match_b.group(2)}({match_b.group(1)})"
    else:
        for k, v in STOCKS_MAP.items():
            if k in title:
                matched_stock = v
                break
                
    return "", "🟡 中", matched_stock, 0

def fetch_and_store_news():
    init_db()
    logs = []
    
    conn = sqlite3.connect("news.db")
    cursor = conn.cursor()
    added_count = 0
    
    media_filter = "site:ctee.com.tw OR site:edn.udn.com OR site:cnyes.com"
    query_with_time = f"({media_filter}) when:3d"
    encoded_query = urllib.parse.quote(query_with_time)
    rss_url = f"https://news.google.com/rss/search?q={encoded_query}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
    
    feed = feedparser.parse(rss_url)
    total_fetched = len(feed.entries)
    logs.append(f"【檢索模式】三大專業財經媒體直抓（近三天原始新聞共 {total_fetched} 篇）")
    
    for entry in feed.entries:
        title = entry.title
        url = entry.link
        source = entry.get('source', {}).get('title', '未知來源')
        raw_published = entry.get('published', '')
        published = parse_pub_date(raw_published)
        
        if any(ex in title for ex in EXCLUDE_KEYWORDS):
            continue
            
        cursor.execute("SELECT id FROM news WHERE url = ?", (url,))
        if cursor.fetchone():
            continue

        core_keyword = clean_title_for_comparison(title)
        if core_keyword and len(core_keyword) >= 4:
            cursor.execute("SELECT id FROM news WHERE title LIKE ?", (f"%{core_keyword}%",))
            existing = cursor.fetchone()
            if existing:
                news_id = existing[0]
                cursor.execute("UPDATE news SET report_count = report_count + 1 WHERE id = ?", (news_id,))
                continue
            
        summary, importance, impact_companies, is_ai = analyze_news_with_ai(title, source)
        
        # 間隔 0.5 秒流速控制，避免瞬間連續請求觸發 RPM 限制
        time.sleep(0.5)
        
        if importance == "⚪ 低":
            continue
            
        try:
            cursor.execute("""
                INSERT INTO news (url, title, source, published_date, summary, importance, impact_companies, report_count, is_ai)
                VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?)
            """, (url, title, source, published, summary, importance, impact_companies, is_ai))
            added_count += 1
        except Exception as e:
            logs.append(f"寫入資料庫錯誤: {e}")
            
    conn.commit()
    conn.close()
    logs.append(f"【執行結果】成功寫入近三日高價值情報 {added_count} 筆。")
    return added_count, logs

def get_news_from_db(search_query="", limit=30, importance_filter=None, sort_by="時間新到舊"):
    init_db()
    conn = sqlite3.connect("news.db")
    cursor = conn.cursor()
    
    sql = "SELECT published_date, title, source, url, summary, importance, impact_companies, report_count, is_ai FROM news WHERE 1=1"
    params = []
    
    if search_query:
        sql += " AND (title LIKE ? OR source LIKE ? OR impact_companies LIKE ? OR summary LIKE ?)"
        params.extend([f"%{search_query}%", f"%{search_query}%", f"%{search_query}%", f"%{search_query}%"])
        
    if importance_filter:
        sql += " AND importance LIKE ?"
        params.append(f"%{importance_filter}%")
        
    if sort_by == "重要性優先":
        sql += " ORDER BY CASE WHEN importance LIKE '%🔴%' THEN 1 WHEN importance LIKE '%🟡%' THEN 2 ELSE 3 END ASC, published_date DESC"
    else:
        sql += " ORDER BY published_date DESC"
        
    sql += " LIMIT ?"
    params.append(limit)
    
    cursor.execute(sql, params)
    rows = cursor.fetchall()
    conn.close()
    return rows
