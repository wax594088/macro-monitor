import feedparser
import sqlite3
import urllib.parse
import os
import re
import json
import time
import requests
from groq import Groq
from email.utils import parsedate_to_datetime
import datetime

# 動態檢測 Gemini SDK 是否安裝
try:
    import google.generativeai as genai
    HAS_GEMINI_SDK = True
except ImportError:
    HAS_GEMINI_SDK = False

# 強制設定台灣台北時區 (UTC+8)
TZ_TAIPEI = datetime.timezone(datetime.timedelta(hours=8))

# 全局快取全台股字典
GLOBAL_STOCKS_MAP = {}

# 全局 API 熔斷開關
AI_CIRCUIT_BROKEN = False

# 1. 垃圾新聞與機器罐頭速報黑名單
EXCLUDE_KEYWORDS = [
    "娛樂", "影劇", "星際", "星座", "八卦", "演唱會", "職棒", 
    "中職", "NBA", "電影", "網紅", "藝人", "電視劇", "綜藝",
    "定期定額", "小資族", "新手", "教學", "開戶",
    "存股", "理財", "買房", "租屋", "信用卡", "現金回饋", "保險",
    "退休", "省錢", "發票", "中獎", "運勢", "生肖",
    "飼主", "寵物", "鄰居", "社會", "車禍", "命案", "外送", "勞基法",
    "專頁", "頻道"
]

# 2. 兼具日常高頻通用語義與技術術語之台股名稱清單
AMBIGUOUS_STOCK_NAMES = {
    # 數量、量詞與程度動詞類
    "大量", "精測", "極機", "飛銳",
    # 抽象形容詞、技術術語與通用概念類
    "國產", "幸福", "大同", "大眾", "第一", "通用", "巨有", "正文", "威盛",
    "亞洲", "新光", "大亞", "高力", "金寶", "巨蛋", "統一", "富邦", "宏碁",
    "聯華", "東元", "中華", "台灣", "太平洋", "長榮", "萬海", "陽明", "佳醫",
    "介面", "材料", "應用", "控制", "系統", "軟體", "先進", "精技",
    # 媒體名稱、出版與高頻詞彙類
    "時報", "商訊", "中央", "優買", "精業"
}

# 3. 高頻權值股新聞簡稱對照表
ALIAS_STOCK_MAP = {
    "台積": "台積電(2330)",
    "發科": "聯發科(2454)"
}

# 4. 無 AI 備援模式下的實質基本面與催化劑觸發詞
CATALYST_TERMS = [
    "營收", "財報", "獲利", "毛利率", "單月EPS", "EPS", "轉虧為盈", "虧轉盈", 
    "大單", "訂單", "擴產", "庫存去化", "急單", "創高", "新高", "爆單", "停利",
    "損益", "本益比", "淨值", "營收新高", "轉盈",
    "重訊", "庫藏股", "併購", "減資", "增資", "現增", "配息", "殖利率", "除權息", 
    "申報轉讓", "法說會", "法說", "改選", "私募", "經營權", "買庫藏股", "CB", "公司債",
    "轉換公司債", "違約", "股東會", "董事會", "子公司", "上市", "上櫃",
    "外資", "投信", "三大法人", "法人", "主力", "買超", "賣超", "借券", "官股",
    "漲停", "跌停", "漲停板", "跌停板", "鎖死", "全額交割",
    "融資", "融券", "追繳", "斷頭", "當沖", "鋸額交易", "違約交割", "暫停交易",
    "半導體", "晶圓代工", "先進封裝", "CoWoS", "CPO", "矽光子", "水冷", "散熱", 
    "液冷", "浸沒式", "伺服器", "ASIC", "IP", "CCL", "PCB", "機器人", "算力", 
    "晶片", "光通訊", "HBM", "玻璃基板", "BBU", "備用電源", "AI PC", "AI 手機", 
    "Edge AI", "邊緣運算", "靜電防護", "ESD", "廠務", "無塵室", "濕製程", "檢測分析",
    "探針卡", "測試介面", "晶圓", "極紫光", "EUV",
    "強韌電網", "重電", "變壓器", "儲能", "綠電", "風電", "軍工", "無人機", 
    "國防", "航太", "低軌衛星", "第三代半導體", "碳化矽", "SiC", "氮化鎵", "GaN",
    "軸承", "折疊機", "Wi-Fi 7", "網通", "車用半導體", "充電樁", "電動車", "車用",
    "新藥", "藥證", "臨床", "CDMO", "醫療", "生技",
    "金管會", "央行", "升息", "降息", "禁令", "通膨", "Fed", "關稅", "制裁",
    "CPI", "PPI", "PCE", "NFP", "非農", "美股", 
    "關稅壁壘", "聯準會"
]

# 5. 無 AI 備援模式下的台股重點對照表（備援字典）
STOCKS_MAP = {
    "台積電": "台積電(2330)", "聯電": "聯電(2303)", "力積電": "力積電(6770)", "世界": "世界(5347)",
    "日月光投控": "日月光投控(3711)", "日月光": "日月光投控(3711)", "京元電子": "京元電子(2449)",
    "萬潤": "萬潤(6187)", "弘塑": "弘塑(3131)", "辛耘": "辛耘(3583)", "家登": "家登(3680)",
    "精測": "精測(6510)", "旺矽": "旺矽(6223)", "穎崴": "穎崴(6515)", "漢唐": "漢唐(2404)",
    "聖暉": "聖暉*(5536)", "亞翔": "亞翔(6139)", "帆宣": "帆宣(6196)",
    "聯發科": "聯發科(2454)", "世芯": "世芯-KY(3661)", "世芯-KY": "世芯-KY(3661)",
    "創意": "創意(3443)", "力旺": "力旺(3529)", "瑞昱": "瑞昱(2379)", "聯詠": "聯詠(3034)",
    "祥碩": "祥碩(5269)", "信驊": "信驊(5274)", "威盛": "威盛(2388)", "神盾": "神盾(6462)",
    "安國": "安國(8054)", "晶心科": "晶心科(6533)", "群聯": "群聯(8299)", "巨有科技": "巨有科技(8227)",
    "M31": "M31(6643)", "圓剛": "圓剛(2417)", "愛普": "愛普*(6531)",
    "鴻海": "鴻海(2317)", "廣達": "廣達(2382)", "緯創": "緯創(3231)", "緯穎": "緯穎(6669)",
    "英業達": "英業達(2356)", "仁寶": "仁寶(2324)", "和碩": "和碩(4938)", "技嘉": "技嘉(2376)",
    "微星": "微星(2377)", "神達": "神達(3706)", "華碩": "華碩(2357)", "宏碁": "宏碁(2353)",
    "金寶": "金寶(2312)", "光寶科": "光寶科(2301)",
    "奇鋐": "奇鋐(3017)", "雙鴻": "雙鴻(3324)", "健策": "健策(3653)", "高力": "高力(8996)",
    "台達電": "台達電(2308)", "勤誠": "勤誠(8210)", "AES-KY": "AES-KY(6781)", "順達": "順達(3211)",
    "新普": "新普(6121)", "晟銘電": "晟銘電(3013)", "建準": "建準(2421)", "富世達": "富世達(6805)",
    "新日興": "新日興(3376)",
    "華城": "華城(1519)", "士電": "士電(1503)", "中興電": "中興電(1513)", "亞力": "亞力(1514)",
    "大亞": "大亞(1609)", "雲豹能源": "雲豹能源(6869)", "森崴能源": "森崴能源(6806)",
    "泓德能源": "泓德能源(6873)", "東元": "東元(1504)", "台汽電": "台汽電(8926)",
    "雷虎": "雷虎(8033)", "漢翔": "漢翔(2634)", "龍德造船": "龍德造船(6753)",
    "長榮航太": "長榮航太(2645)", "千附精密": "千附精密(6829)", "昇達科": "昇達科(3491)",
    "事欣科": "事欣科(4916)", "全訊": "全訊(5222)", "寶一": "寶一(8222)",
    "所羅門": "所羅門(2359)", "昆盈": "昆盈(2365)", "羅昇": "羅昇(8374)", "盟立": "盟立(2464)",
    "上銀": "上銀(2049)", "川湖": "川湖(2059)", "聯鈞": "聯鈞(3450)", "華星光": "華星光(4979)",
    "波若威": "波若威(3163)", "前鼎": "前鼎(4908)", "智邦": "智邦(2345)", "啟碁": "啟碁(6285)",
    "中磊": "中磊(5388)", "正文": "正文(4906)",
    "台光電": "台光電(2383)", "台燿": "台燿(6274)", "金像電": "金像電(2368)", "華通": "華通(2313)",
    "健鼎": "健鼎(3044)", "欣興": "欣興(3037)", "景碩": "景碩(3189)", "南電": "南電(8046)",
    "國巨": "國巨(2327)", "華新科": "華新科(2492)", "聯茂": "聯茂(6213)",
    "大立光": "大立光(3008)", "玉晶光": "玉晶光(3406)", "亞光": "亞光(3019)", "先進光": "先進光(3362)",
    "胡連": "胡連(6279)", "同致": "同致(3552)",
    "藥華藥": "藥華藥(6446)", "美時": "美時(1795)", "保瑞": "保瑞(6472)", "科懋": "科懋(6496)",
    "寶島科": "寶島科(5312)", "合一": "合一(4743)", "中天": "中天(4128)",
    "長榮": "長榮(2603)", "陽明": "陽明(2609)", "萬海": "萬海(2615)", "華航": "華航(2610)",
    "長榮航": "長榮航(2618)", "台塑": "台塑(1301)", "南亞": "南亞(1303)", "台化": "台化(1326)",
    "中鋼": "中鋼(2002)", "台泥": "台泥(1101)", "亞泥": "亞泥(1102)",
    "富邦金": "富邦金(2881)", "國泰金": "國泰金(2882)", "中信金": "中信金(2891)",
    "兆豐金": "兆豐金(2886)", "玉山金": "玉山金(2884)", "元大金": "元大金(2885)",
    "台新金": "台新金(2887)", "永豐金": "永豐金(2890)", "第一金": "第一金(2892)",
    "華南金": "華南金(2880)", "開發金": "凱基金(2883)", "凱基金": "凱基金(2883)",
    "合庫金": "合庫金(5880)", "上海商銀": "上海商銀(5876)",
    "中華資安": "中華資安(7765)"
}

def load_all_taiwan_stocks():
    """自動透過 FinMind API 下載最新全台股清單"""
    global GLOBAL_STOCKS_MAP
    if GLOBAL_STOCKS_MAP:
        return GLOBAL_STOCKS_MAP

    url = "https://api.finmindtrade.com/api/v4/data?dataset=TaiwanStockInfo"
    try:
        res = requests.get(url, timeout=5)
        if res.status_code == 200:
            data = res.json().get("data", [])
            stocks = {}
            for item in data:
                stock_id = item.get("stock_id", "").strip()
                stock_name = item.get("stock_name", "").strip()
                if stock_id.isdigit() and len(stock_id) == 4 and stock_name:
                    stocks[stock_name] = f"{stock_name}({stock_id})"
            if stocks:
                GLOBAL_STOCKS_MAP = stocks
                return stocks
    except Exception:
        pass

    return STOCKS_MAP

def extract_stocks_by_rules(title):
    """由 Python 主導比對全台股清單，優先比對長字串並剔除子字串重疊與通用詞"""
    pure_title = re.sub(r'\s*-\s*.*$', '', title).strip()
    
    stocks_map = load_all_taiwan_stocks()
    matched = []
    occupied_spans = []

    for match in re.finditer(r'([\u4e00-\u9fa5\w\-]+)[\(（](\d{4})[\)）]', pure_title):
        name, code = match.group(1), match.group(2)
        matched.append(f"{name}({code})")
        occupied_spans.append((match.start(), match.end()))

    for alias, full_str in ALIAS_STOCK_MAP.items():
        if alias in pure_title and full_str not in matched:
            matched.append(full_str)

    sorted_stock_names = sorted(stocks_map.keys(), key=len, reverse=True)

    for name in sorted_stock_names:
        full_str = stocks_map[name]
        
        if name in AMBIGUOUS_STOCK_NAMES:
            continue
            
        if len(name) >= 2 and name in pure_title and full_str not in matched:
            for match in re.finditer(re.escape(name), pure_title):
                start, end = match.start(), match.end()
                
                is_overlapping = any(
                    o_start <= start and end <= o_end 
                    for o_start, o_end in occupied_spans
                )
                
                if not is_overlapping:
                    matched.append(full_str)
                    occupied_spans.append((start, end))
                    break

    res_str = "、".join(matched) if matched else ""
    
    if any(icon in res_str for icon in ["🔴", "🟡", "⚪", "⚫", "無"]):
        return ""
        
    return res_str

def init_db():
    """初始化資料庫，包含強制建表與補齊缺漏欄位邏輯"""
    try:
        with sqlite3.connect("news.db", timeout=20.0) as conn:
            cursor = conn.cursor()
            
            try:
                cursor.execute("PRAGMA journal_mode=WAL;")
            except sqlite3.OperationalError:
                pass

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS news (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    url TEXT UNIQUE,
                    title TEXT,
                    source TEXT,
                    published_date TEXT,
                    summary TEXT,
                    importance TEXT,
                    category TEXT,
                    impact_companies TEXT,
                    report_count INTEGER DEFAULT 1,
                    is_ai INTEGER DEFAULT 1
                )
            """)

            # 檢查並自動補充缺少的欄位
            cursor.execute("PRAGMA table_info(news);")
            existing_cols = [col[1] for col in cursor.fetchall()]

            required_cols = {
                "summary": "TEXT",
                "importance": "TEXT",
                "category": "TEXT",
                "impact_companies": "TEXT",
                "report_count": "INTEGER DEFAULT 1",
                "is_ai": "INTEGER DEFAULT 1"
            }

            for col_name, col_type in required_cols.items():
                if col_name not in existing_cols:
                    try:
                        cursor.execute(f"ALTER TABLE news ADD COLUMN {col_name} {col_type};")
                    except Exception:
                        pass

            conn.commit()
    except Exception:
        pass
    clean_old_news()

def clean_old_news():
    try:
        with sqlite3.connect("news.db", timeout=20.0) as conn:
            cursor = conn.cursor()
            cutoff_date = (datetime.datetime.now(TZ_TAIPEI) - datetime.timedelta(days=3)).strftime("%Y-%m-%d %H:%M:%S")
            cursor.execute("DELETE FROM news WHERE published_date < ?", (cutoff_date,))
            conn.commit()
    except Exception:
        pass

def clear_all_news():
    """徹底刪除舊表並重新建表，徹底清除缺欄位引起的 sqlite3 錯誤"""
    try:
        with sqlite3.connect("news.db", timeout=20.0) as conn:
            cursor = conn.cursor()
            cursor.execute("DROP TABLE IF EXISTS news;")
            conn.commit()
        init_db()
        return True
    except Exception:
        return False

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
    cleaned = re.sub(r'^(快訊|注意|特報|即時|焦點|頭條|商情|鉅亨速報|Factset\s*最新調查\s*[:：]?)[／/！!：:\-\s]*', '', cleaned)
    cleaned = re.sub(r'[^\u4e00-\u9fa5a-zA-Z0-9]', '', cleaned)
    return cleaned

def clean_url_params(url):
    """剔除網址中夾帶的列印與無效參數"""
    url = re.sub(r'[\?&](print|isPrint|output=print)=[^&]*', '', url, flags=re.IGNORECASE)
    url = re.sub(r'\?&', '?', url)
    return url.rstrip('?&')

def parse_ai_response(text, title):
    """精準清洗 AI 回傳，包含 6 大核心類型解析"""
    summary, importance, category = "", "⚪", "產業"
    for line in text.split("\n"):
        line_str = line.strip()
        if "摘要：" in line_str:
            val = line_str.replace("摘要：", "").strip()
            summary = re.sub(r'^[＊\*\s]+', '', val)
        elif "重要性：" in line_str:
            val = line_str.replace("重要性：", "").strip()
            if "🔴" in val:
                importance = "🔴"
            elif "🟡" in val:
                importance = "🟡"
            else:
                importance = "⚪"
        elif "類別：" in line_str:
            val = line_str.replace("類別：", "").strip()
            valid_cats = ["財報", "重訊", "國際", "指數", "產業", "總經"]
            for cat in valid_cats:
                if cat in val:
                    category = cat
                    break

    impact_companies = extract_stocks_by_rules(title)
    
    if any(icon in impact_companies for icon in ["🔴", "🟡", "⚪", "⚫", "無"]):
        impact_companies = ""

    return summary, importance, category, impact_companies, 1

def fallback_rule_analysis(title):
    """無 AI 模式下的備援規則比對"""
    has_catalyst = any(term in title for term in CATALYST_TERMS)
    if not has_catalyst:
        return "", "⚪", "產業", "", 0

    matched_stock = extract_stocks_by_rules(title)
    return "", "🟡", "產業", matched_stock, 0

def analyze_news_with_ai(title, source):
    """AI 分析功能，具備超時限制與額度耗盡自動熔斷機制"""
    global AI_CIRCUIT_BROKEN

    if AI_CIRCUIT_BROKEN:
        return fallback_rule_analysis(title)

    prompt = f"""
    你是一個專業的台股操盤手。請評估以下新聞是否具備實質影響台股股價或產業預期的潛力：
    新聞標題：{title}
    新聞來源：{source}

    判斷標準：
    - 若屬於一般理財、生活消費、社會新聞、寵物、無具體公司財報/訂單的小道消息、或與台股無關，請將重要性設為「⚪ 低」。
    - 若屬於核心維度（政策紅利、突發風險、基本面拐點、總經變數、供應鏈衝擊），請將重要性設為「🔴 高」或「🟡 中」。

    類別選項（僅限填寫其中一項）：財報、重訊、國際、指數、產業、總經
    - 財報：單月營收、季報、年報、EPS、獲利表現。
    - 重訊：法說會、庫藏股、減資增資、併購、重大營運公告。
    - 國際：美股動態、國際財經事件、海外大廠、地緣政治。
    - 指數：大盤走勢、類股指數、盤中速報、法人籌碼。
    - 產業：供應鏈、訂單、擴產、技術突破、新產品。
    - 總經：央行利率、聯準會(Fed)、通膨數據(CPI/PPI)、政策。

    請嚴格依照下列格式回傳（嚴禁在欄位內填寫任何多餘的解釋或理由）：
    摘要：[僅填一句話說明事件本質]
    重要性：[僅填 🔴高、🟡中、或 ⚪低]
    類別：[僅填 財報、重訊、國際、指數、產業、總經 其中一項]
    """
    
    groq_key = os.environ.get("GROQ_API_KEY")
    gemini_key = os.environ.get("GEMINI_API_KEY")

    # 1. 嘗試 Groq 70B (超時 4 秒)
    if groq_key:
        try:
            client = Groq(api_key=groq_key, timeout=4.0)
            response = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1
            )
            return parse_ai_response(response.choices[0].message.content.strip(), title)
        except Exception as e:
            err_str = str(e).lower()
            if any(k in err_str for k in ["rate_limit", "quota", "429", "resource_exhausted"]):
                AI_CIRCUIT_BROKEN = True
                return fallback_rule_analysis(title)

    # 2. 嘗試 Gemini 1.5 Flash (超時 4 秒)
    if gemini_key and HAS_GEMINI_SDK and not AI_CIRCUIT_BROKEN:
        try:
            genai.configure(api_key=gemini_key)
            model = genai.GenerativeModel("gemini-1.5-flash")
            response = model.generate_content(prompt, request_options={'timeout': 4.0})
            return parse_ai_response(response.text.strip(), title)
        except Exception as e:
            err_str = str(e).lower()
            if any(k in err_str for k in ["quota", "resource_exhausted", "429"]):
                AI_CIRCUIT_BROKEN = True
                return fallback_rule_analysis(title)

    # 3. 嘗試 Groq 8B (超時 3 秒)
    if groq_key and not AI_CIRCUIT_BROKEN:
        try:
            client = Groq(api_key=groq_key, timeout=3.0)
            response = client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1
            )
            return parse_ai_response(response.choices[0].message.content.strip(), title)
        except Exception as e:
            err_str = str(e).lower()
            if any(k in err_str for k in ["rate_limit", "quota", "429"]):
                AI_CIRCUIT_BROKEN = True

    return fallback_rule_analysis(title)

def fetch_and_store_news():
    """抓取新聞、進行 AI 解析並儲存至 SQLite，具備安全併發與 Migration 控制"""
    global AI_CIRCUIT_BROKEN
    AI_CIRCUIT_BROKEN = False  # 每輪啟動重置熔斷狀態
    
    init_db()
    logs = []
    
    added_count = 0
    total_fetched = 0
    
    media_targets = [
        ("工商時報", "site:ctee.com.tw"),
        ("經濟日報", "site:edn.udn.com"),
        ("鉅亨網", "site:cnyes.com")
    ]
    
    with sqlite3.connect("news.db", timeout=20.0) as conn:
        cursor = conn.cursor()
        
        for media_name, media_site in media_targets:
            query_with_time = f"{media_site} when:3d"
            encoded_query = urllib.parse.quote(query_with_time)
            rss_url = f"https://news.google.com/rss/search?q={encoded_query}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
            
            feed = feedparser.parse(rss_url)
            site_fetched = len(feed.entries)
            total_fetched += site_fetched
            logs.append(f"【檢索】{media_name}（近三天抓取到 {site_fetched} 篇原始新聞）")
            
            for entry in feed.entries:
                title = entry.title
                url = clean_url_params(entry.link)
                source = entry.get('source', {}).get('title', media_name)
                raw_published = entry.get('published', '')
                published = parse_pub_date(raw_published)
                
                if any(ex in title for ex in EXCLUDE_KEYWORDS):
                    continue

                clean_t = clean_title_for_comparison(title)
                invalid_titles = ["鉅亨網", "鉅亨網 - 鉅亨網", "經濟日報", "工商時報", "cnyes.com", "ctee.com.tw", "edn.udn.com", "頭條新聞"]
                if title.strip() in invalid_titles or len(clean_t) < 5:
                    continue

                if "cnyes.com" in url and "/news/id/" not in url:
                    continue
                    
                cursor.execute("SELECT id FROM news WHERE url = ?", (url,))
                if cursor.fetchone():
                    continue

                if clean_t and len(clean_t) >= 6:
                    cursor.execute("SELECT id, importance FROM news WHERE title LIKE ?", (f"%{clean_t}%",))
                    existing = cursor.fetchone()
                    if existing:
                        news_id = existing[0]
                        cursor.execute("UPDATE news SET report_count = report_count + 1, published_date = ? WHERE id = ?", (published, news_id))
                        conn.commit()
                        continue
                    
                summary, importance, category, impact_companies, is_ai = analyze_news_with_ai(title, source)
                
                if is_ai == 1 and not AI_CIRCUIT_BROKEN:
                    time.sleep(0.2)
                    
                if importance == "⚪":
                    continue
                    
                try:
                    cursor.execute("""
                        INSERT INTO news (url, title, source, published_date, summary, importance, category, impact_companies, report_count, is_ai)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
                    """, (url, title, source, published, summary, importance, category, impact_companies, is_ai))
                    conn.commit()
                    added_count += 1
                except Exception as e:
                    logs.append(f"寫入資料庫錯誤: {e}")
                    
    if AI_CIRCUIT_BROKEN:
        logs.append("【警告】檢測到 AI API 額度用盡或回應超時，已自動熔斷並切換至本地規則模式。")
        
    logs.append(f"【執行結果】三大媒體總計抓取 {total_fetched} 篇，成功寫入高價值情報 {added_count} 筆。")
    return added_count, logs

def get_news_from_db(search_query="", limit=50, importance_filter=None, sort_by="時間新到舊"):
    """純讀取新聞資料庫，具備容錯修補機制"""
    init_db()
    
    sql = "SELECT published_date, title, source, url, summary, importance, category, impact_companies, report_count, is_ai FROM news WHERE 1=1"
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
    
    try:
        with sqlite3.connect("news.db", timeout=20.0) as conn:
            cursor = conn.cursor()
            cursor.execute(sql, params)
            return cursor.fetchall()
    except sqlite3.OperationalError:
        return []
