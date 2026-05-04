"""
Taiwan Stock Industry Mapper
=============================
從 TWSE / TPEX 官方 API 取得每支股票的產業別代碼，
並映射到可讀的族群名稱。

資料來源：
  - TWSE (上市): https://openapi.twse.com.tw/v1/opendata/t187ap03_L
  - TPEX (上櫃): https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap03_O

快取：data/stock_industries.json（24h TTL）
"""

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Optional

import requests
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

from src.utils.logger import get_logger

logger = get_logger(__name__)

# ── 快取設定 ──────────────────────────────────────────────────────────────────
_PROJECT_ROOT = Path(__file__).parent.parent.parent
CACHE_FILE = _PROJECT_ROOT / "data" / "cache" / "stock_industries.json"
CACHE_TTL_HOURS = 24

# ── TWSE / TPEX 官方產業別代碼 → 族群名稱 ────────────────────────────────────
# 代碼 01-29 由 TWSE 官方定義（TPEX 共用相同代碼系統）
# 代碼 30+ 為近年新增或 TPEX 擴充類別
INDUSTRY_CODE_TO_SECTOR: Dict[str, str] = {
    # ── 傳統產業（01-20）─────────────────────────────────────────────
    "01": "水泥工業",     # 台泥、亞泥
    "02": "食品工業",     # 味全、統一
    "03": "塑膠工業",     # 台塑、南亞
    "04": "紡織纖維",     # 遠東新、儒鴻
    "05": "電機機械",     # 士電、東元
    "06": "電器電纜",     # 華新、大亞、聲寶
    "07": "化學工業",     # 部分化工（已多併入 21）
    "08": "玻璃陶瓷",     # 台玻、冠軍
    "09": "造紙工業",     # 正隆、華紙
    "10": "鋼鐵工業",     # 中鋼、東和鋼鐵
    "11": "橡膠工業",     # 正新、台橡
    "12": "汽車工業",     # 東陽、中華車
    "13": "電子工業",     # 舊類（多已細分至 24-31）
    "14": "建材營造",     # 三地開發等
    "15": "航運業",       # 長榮、裕民、陽明
    "16": "觀光餐旅",     # 六福、國賓
    "17": "金融保險",     # 彰銀、富邦金、國泰金
    "18": "貿易百貨",     # 遠百、三商
    "19": "綜合",
    "20": "其他",
    # ── 電子/科技細分類（21-31）─────────────────────────────────────
    # 驗證依據：TWSE openapi.twse.com.tw/v1/opendata/t187ap03_L 實際資料
    "21": "化學工業",     # 東鹼、永光、興農（化學）
    "22": "生技醫療",     # 葡萄王、生達、五鼎、杏輝（生技醫療）
    "23": "電力及天然氣", # 台塑化、台汽電、大台北、欣天然
    "24": "半導體業",     # 台積電、聯電、旺宏、華邦電
    "25": "電腦週邊",     # 光寶科、仁寶、精英、佳世達
    "26": "光電業",       # 友達、億光、中環、錸德、佳能
    "27": "通信網路",     # 中華電、智邦、友訊、台揚
    "28": "電子零組件",   # 台達電、華通、乙盛-KY、德宏
    "29": "電子通路",     # 聯強、燦坤、精技、華立
    "30": "資訊服務",     # 資通、凌群、三商電、敦陽科
    "31": "其他電子",     # 鴻海、金寶、致茂、鴻準
    # ── 近年新增類別（32+）────────────────────────────────────────────
    "32": "電子商務",
    "33": "觀光餐旅",     # TPEX 擴充（代碼與 TWSE 16 相同意義）
    "35": "綠能環保",     # 世紀風電、上緯投控
    "36": "數位雲端",     # 一零四、GOGOLOOK、伊雲谷
    "37": "運動休閒",     # 岱宇、喬山、世界健身
    "38": "居家生活",     # 橋椿、峰源-KY
    "91": "存託憑證",     # DR（美德醫療-DR、康師傅-DR）
}


def _fetch_twse_industries() -> Dict[str, str]:
    """從 TWSE API 取得上市股票的產業別代碼。
    Returns: {股票代號: 產業別代碼}
    """
    url = "https://openapi.twse.com.tw/v1/opendata/t187ap03_L"
    try:
        resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15, verify=False)
        resp.raise_for_status()
        result = {}
        for item in resp.json():
            code = item.get("公司代號", "").strip()
            industry = item.get("產業別", "").strip()
            if code and code.isdigit() and len(code) == 4 and industry:
                result[code] = industry
        logger.info(f"TWSE: 取得 {len(result)} 支上市股票產業別")
        return result
    except Exception as e:
        logger.warning(f"TWSE 產業別 API 失敗: {e}")
        return {}


def _fetch_tpex_industries() -> Dict[str, str]:
    """從 TPEX API 取得上櫃股票的產業別代碼。
    Returns: {股票代號: 產業別代碼}
    """
    url = "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap03_O"
    try:
        resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15, verify=False)
        resp.raise_for_status()
        result = {}
        for item in resp.json():
            code = item.get("SecuritiesCompanyCode", "").strip()
            industry = item.get("SecuritiesIndustryCode", "").strip()
            if code and code.isdigit() and len(code) == 4 and industry:
                result[code] = industry
        logger.info(f"TPEX: 取得 {len(result)} 支上櫃股票產業別")
        return result
    except Exception as e:
        logger.warning(f"TPEX 產業別 API 失敗: {e}")
        return {}


def _load_cache() -> Optional[Dict[str, str]]:
    """載入快取（若仍在 TTL 內）。Returns: {股票代號: 產業別代碼} or None"""
    if not CACHE_FILE.exists():
        return None
    try:
        with open(CACHE_FILE, encoding="utf-8") as f:
            payload = json.load(f)
        cached_at = datetime.fromisoformat(payload["cached_at"])
        if datetime.now() - cached_at < timedelta(hours=CACHE_TTL_HOURS):
            return payload["industries"]
    except Exception:
        pass
    return None


def _save_cache(industries: Dict[str, str]) -> None:
    """儲存快取"""
    try:
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(
                {"cached_at": datetime.now().isoformat(), "industries": industries},
                f,
                ensure_ascii=False,
            )
    except Exception as e:
        logger.warning(f"寫入產業別快取失敗: {e}")


def get_stock_industries(use_cache: bool = True) -> Dict[str, str]:
    """取得股票代號 → 產業別代碼的映射。

    Returns:
        {股票代號: 產業別代碼}，例如 {'2330': '22', '5243': '26'}
    """
    if use_cache:
        cached = _load_cache()
        if cached is not None:
            return cached

    logger.info("從 TWSE/TPEX 取得產業別資料...")
    industries: Dict[str, str] = {}
    industries.update(_fetch_twse_industries())
    industries.update(_fetch_tpex_industries())

    if industries:
        _save_cache(industries)
        logger.info(f"共取得 {len(industries)} 支股票產業別代碼")
    else:
        logger.warning("無法取得產業別資料，族群過濾將降級為代碼前綴模式")

    return industries


def get_sector_name(industry_code: str) -> str:
    """將產業別代碼轉為族群名稱。未知代碼回傳 '其他'。"""
    return INDUSTRY_CODE_TO_SECTOR.get(industry_code, "其他")
