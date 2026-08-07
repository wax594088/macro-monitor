import feedparser
import sqlite3
import urllib.parse
import os
import re
import json
from groq import Groq
from email.utils import parsedate_to_datetime
import datetime

# 強制設定台灣台北時區 (UTC+8)
TZ_TAIPEI = datetime.timezone(datetime.timedelta(hours=8))

# 1. 垃圾新聞黑名單
EXCLUDE_KEYWORDS = [
    "娛樂", "影劇", "星際", "星座", "八卦", "演唱會", "職棒", 
    "中職", "NBA", "電影", "網紅", "藝人", "電視劇", "綜藝",
    "定期定額", "小資族", "新手", "教學", "開戶", "ETF掛牌",
    "存股", "理財", "買房", "租屋", "信用卡", "現金回饋", "保險",
    "退休", "省錢", "發票", "中獎", "運勢", "生肖",
    "飼主", "寵物", "鄰居", "社會", "車禍", "命案", "外送", "勞基法"
]

# 2. 無 AI 備援模式下的實質基本面與催化劑觸發詞
CATALYST_TERMS = [
    # 財務指標與營運績效
    "營收", "財報", "獲利", "毛利率", "單月EPS", "EPS", "轉虧為盈", "虧轉盈", 
    "大單", "訂單", "擴產", "庫存去化", "急單", "創高", "新高", "爆單", "停利",
    "損益", "本益比", "淨值", "營收新高", "轉盈",
    
    # 資本動作與公司治理
    "重訊", "庫藏股", "併購", "減資", "增資", "現增", "配息", "殖利率", "除權息", 
    "申報轉讓", "法說會", "法說", "改選", "私募", "經營權", "買庫藏股", "CB", "公司債",
    "轉換公司債", "違約", "股東會", "董事會", "子公司", "上市", "上櫃",
    
    # 籌碼動態與市場交易機制
    "外資", "投信", "三大法人", "法人", "主力", "買超", "賣超", "借券", "官股",
    "漲停", "跌停", "漲停板", "跌停板", "鎖死", "處置股", "注意股", "全額交割",
    "融資", "融券", "追繳", "斷頭", "當沖", "鉅額交易", "違約交割", "暫停交易",
    
    # AI、半導體與先進製造
    "半導體", "晶圓代工", "先進封裝", "CoWoS", "CPO", "矽光子", "水冷", "散熱", 
    "液冷", "浸沒式", "伺服器", "ASIC", "IP", "CCL", "PCB", "機器人", "算力", 
    "晶片", "光通訊", "HBM", "玻璃基板", "BBU", "備用電源", "AI PC", "AI 手機", 
    "Edge AI", "邊緣運算", "靜電防護", "ESD", "廠務", "無塵室", "濕製程", "檢測分析",
    "探針卡", "測試介面", "晶圓", "極紫光", "EUV",
    
    # 重電、綠能、軍工、低軌衛星與車用
    "強韌電網", "重電", "變壓器", "儲能", "綠電", "風電", "軍工", "無人機", 
    "國防", "航太", "低軌衛星", "第三代半導體", "碳化矽", "SiC", "氮化鎵", "GaN",
    "軸承", "折疊機", "Wi-Fi 7", "網通", "車用半導體", "充電樁", "電動車", "車用",
    
    # 生技與醫療
    "新藥", "藥證", "臨床", "CDMO", "醫療", "生技",
    
    # 總體經濟與國際政經
    "金管會", "央行", "升息", "降息", "禁令", "通膨", "Fed", "關稅", "制裁",
    "CPI", "PPI", "PCE", "NFP", "非農", "美股", "台幣", "匯率", "景氣燈號",
    "關稅壁壘", "聯準會"
]

# 3. 無 AI 備援模式下的台股重點對照表
STOCKS_MAP = {
    # 晶圓代工 / 封測 / 設備 / 廠務
    "台積電": "台積電(2330)", "聯電": "聯電(2303)", "力積電": "力積電(6770)", "世界": "世界(5347)",
    "日月光投控": "日月光投控(3711)", "日月光": "日月光投控(3711)", "京元電子": "京元電子(2449)",
    "萬潤": "萬潤(6187)", "弘塑": "弘塑(3131)", "辛耘": "辛耘(3583)", "家登": "家登(3680)",
    "精測": "精測(6510)", "旺矽": "旺矽(6223)", "穎崴": "穎崴(6515)", "漢唐": "漢唐(2404)",
    "聖暉": "聖暉*(5536)", "亞翔": "亞翔(6139)", "帆宣": "帆宣(6196)",

    # IC 設計 / IP 矽智財
    "聯發科": "聯發科(2454)", "世芯": "世芯-KY(3661)", "世芯-KY": "世芯-KY(3661)",
    "創意": "創意(3443)", "力旺": "力旺(3529)", "瑞昱": "瑞昱(2379)", "聯詠": "聯詠(3034)",
    "祥碩": "祥碩(5269)", "信驊": "信驊(5274)", "威盛": "威盛(2388)", "神盾": "神盾(6462)",
    "安國": "安國(8054)", "晶心科": "晶心科(6533)", "群聯": "群聯(8299)", "巨有科技": "巨有科技(8227)",
    "M31": "M31(6643)", "圓剛": "圓剛(2417)", "愛普": "愛普*(6531)",

    # AI 伺服器 / 代工大廠 / 組裝
    "鴻海": "鴻海(2317)", "廣達": "廣達(2382)", "緯創": "緯創(3231)", "緯穎": "緯穎(6669)",
    "英業達": "英業達(2356)", "仁寶": "仁寶(2324)", "和碩": "和碩(4938)", "技嘉": "技嘉(2376)",
    "微星": "微星(2377)", "神達": "神達(3706)", "華碩": "華碩(2357)", "宏碁": "宏碁(2353)",
    "金寶": "金寶(2312)", "光寶科": "光寶科(2301)",

    # 散熱 / 機殼 / 電源 / BBU / 折疊機
    "奇鋐": "奇鋐(3017)", "雙鴻": "雙鴻(3324)", "健策": "健策(3653)", "高力": "高力(8996)",
    "台達電": "台達電(2308)", "勤誠": "勤誠(8210)", "AES-KY": "AES-KY(6781)", "順達": "順達(3211)",
    "新普": "新普(6121)", "晟銘電": "晟銘電(3013)", "建準": "建準(2421)", "富世達": "富世達(6805)",
    "新日興": "新日興(3376)",

    # 重電 / 綠能 / 線纜 / 儲能
    "華城": "華城(1519)", "士電": "士電(1503)", "中興電": "中興電(1513)", "亞力": "亞力(1514)",
    "大亞": "大亞(1609)", "雲豹能源": "雲豹能源(6869)", "森崴能源": "森崴能源(6806)",
    "泓德能源": "泓德能源(6873)", "東元": "東元(1504)", "台汽電": "台汽電(8926)",

    # 軍工 / 航太 / 低軌衛星
    "雷虎": "雷虎(8033)", "漢翔": "漢翔(2634)", "龍德造船": "龍德造船(6753)",
    "長榮航太": "長榮航太(2645)", "千附精密": "千附精密(6829)", "昇達科": "昇達科(3491)",
    "事欣科": "事欣科(4916)", "全訊": "全訊(5222)", "寶一": "寶一(8222)",

    # 機器人 / 自動化 / 矽光子 / 網通
    "所羅門": "所羅門(2359)", "昆盈": "昆盈(2365)", "羅昇": "羅昇(8374)", "盟立": "盟立(2464)",
    "上銀": "上銀(2049)", "川湖": "川湖(2059)", "聯鈞": "聯鈞(3450)", "華星光": "華星光(4979)",
    "波若威": "波若威(3163)", "前鼎": "前鼎(4908)", "智邦": "智邦(2345)", "啟碁": "啟碁(6285)",
    "中磊": "中磊(5388)", "正文": "正文(4906)",

    # PCB / CCL / 被動元件
    "台光電": "台光電(2383)", "台燿": "台燿(6274)", "金像電": "金像電(2368)", "華通": "華通(2313)",
    "健鼎": "健鼎(3044)", "欣興": "欣興(3037)", "景碩": "景碩(3189)", "南電": "南電(8046)",
    "國巨": "國巨(2327)", "華新科": "華新科(2492)", "聯茂": "聯茂(6213)",

    # 光學 / 車用
    "大立光": "大立光(3008)", "玉晶光": "玉晶光(3406)", "亞光": "亞光(3019)", "先進光": "先進光(3362)",
    "胡連": "胡連(6279)", "同致": "同致(3552)",

    # 生技醫療
    "藥華藥": "藥華藥(6446)", "美時": "美時(1795)", "保瑞": "保瑞(6472)", "科懋": "科懋(6496)",
    "寶島科": "寶島科(5312)", "合一": "合一(4743)", "中天": "中天(4128)",

    # 航運 / 傳統產業
    "長榮": "長榮(2603)", "陽明": "陽明(2609)", "萬海": "萬海(2615)", "華航": "華航(2610)",
    "長榮航": "長榮航(2618)", "台塑": "台塑(1301)", "南亞": "南亞(1303)", "台化": "台化(1326)",
    "中鋼": "中鋼(2002)", "台泥": "台泥(1101)", "亞泥": "亞泥(1102)",

    # 金融權值
    "富邦金": "富邦金(2881)", "國泰金": "國泰金(2882)", "中信金": "中信金(2891)",
    "兆豐金": "兆豐金(2886)", "玉山金": "玉山金(2884)", "元大金": "元大金(2885)",
    "台新金": "台新金(2887)", "永豐金": "永豐金(2890)", "第一金": "第一金(2892)",
    "華南金": "華南金(2880)", "開發金": "凱基金(2883)", "凱基金": "凱基金(2883)",
    "合庫金": "合庫金(5880)", "上海商銀": "上海商銀(5876)"
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
    """去除前綴與媒體尾綴，保留 10 個核心特徵字比對重複新聞"""
    cleaned = re.sub(r' - [^-]+$', '', title)
    cleaned = re.sub(r'^[【《\[\(][^】》\]\)]+[】》\]\)]', '', cleaned)
    cleaned = re.sub(r'^(快訊|注意|特報|即時|焦點|頭條|商情)[／/！!：:\-\s]*', '', cleaned)
    cleaned = re.sub(r'[^\u4e00-\u9fa5a-zA-Z0-9]', '', cleaned)
    return cleaned[:10]

def analyze_news_with_ai(title, source):
    """Part 1: AI 額度足夠時的精準解析"""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        return fallback_rule_analysis(title)
        
    try:
        client = Groq(api_key=api_key)
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
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1
        )
        text = response.choices[0].message.content.strip()
        
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
    except Exception:
        # API 滿載/異常時，平滑切換至 Part 2 的強規則備援
        return fallback_rule_analysis(title)

def fallback_rule_analysis(title):
    """Part 2: AI 額度不足時的強規則備援解析"""
    # 1. 基本面與催化劑詞彙過濾
    has_catalyst = any(term in title for term in CATALYST_TERMS)
    if not has_catalyst:
        return "", "⚪ 低", "", 0

    matched_stock = ""
    
    # 2. 多重正則表達式比對格式：
    # 模式 A: 台積電(2330) 或 台積電（2330）
    match_a = re.search(r'([\u4e00-\u9fa5\w\-]+)[\(（](\d{4})[\)）]', title)
    # 模式 B: 2330台積電 或 2330 台積電
    match_b = re.search(r'(\d{4})\s*([\u4e00-\u9fa5\w\-]+)', title)
    
    if match_a:
        matched_stock = f"{match_a.group(1)}({match_a.group(2)})"
    elif match_b and len(match_b.group(2)) >= 2:
        matched_stock = f"{match_b.group(2)}({match_b.group(1)})"
    else:
        # 模式 C: 比對對照表字典
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
    
    # 直接鎖定三大專業財經媒體，進行單趟全量抓取
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
        
        # 1. 垃圾關鍵字黑名單跳過
        if any(ex in title for ex in EXCLUDE_KEYWORDS):
            continue
            
        # 2. 網址完全相同跳過
        cursor.execute("SELECT id FROM news WHERE url = ?", (url,))
        if cursor.fetchone():
            continue

        # 3. 標題核心字查重，重複議題則更新曝光總數 (report_count + 1)
        core_keyword = clean_title_for_comparison(title)
        if core_keyword and len(core_keyword) >= 4:
            cursor.execute("SELECT id FROM news WHERE title LIKE ?", (f"%{core_keyword}%",))
            existing = cursor.fetchone()
            if existing:
                news_id = existing[0]
                cursor.execute("UPDATE news SET report_count = report_count + 1 WHERE id = ?", (news_id,))
                continue
            
        # 4. 解析新聞（自動判斷走向 AI 語意或規則備援）
        summary, importance, impact_companies, is_ai = analyze_news_with_ai(title, source)
        
        # 5. 剔除低價值新聞
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
