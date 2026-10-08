"""
Taiwan Stock Sub-Industry Mapper（細產業對照）
================================================
從櫃買中心「產業價值鏈資訊平台」取得細產業分類與成分股。

資料來源：https://ic.tpex.org.tw/
  - 首頁列出所有產業鏈（如 J000 被動元件、L000 印刷電路板、D000 半導體）
  - 每個產業鏈頁面 introduce.php?ic=XXXX 內含多個細產業
    （div id="companyList_J800" title="濾波器、振盪器"），
    其下列出本國上市 / 上櫃 / 興櫃公司與知名外國企業

只保留「本國上市」與「本國上櫃」公司（興櫃、外國企業沒有本系統的日K資料）。
同一檔股票可能屬於多個細產業。

快取：data/cache/sub_industries.json（TTL 由 settings.ma_cross.sub_industry_cache_ttl_hours 控制）
"""

import html
import json
import re
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

import requests
import urllib3

from src.utils.logger import get_logger

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = get_logger(__name__)

_PROJECT_ROOT = Path(__file__).parent.parent.parent
CACHE_FILE = _PROJECT_ROOT / "data" / "cache" / "sub_industries.json"

BASE_URL = "https://ic.tpex.org.tw"
_HEADERS = {"User-Agent": "Mozilla/5.0"}

# 只納入有日K資料的市場別
_ALLOWED_SECTIONS = ("本國上市公司", "本國上櫃公司")

_CHAIN_LINK_RE = re.compile(r"introduce\.php\?ic=([0-9A-Z]{4})")
_PAGE_TITLE_RE = re.compile(r"<h3>(.*?)產業鏈簡介</h3>")
_COMPANY_LIST_RE = re.compile(
    r'<div id="companyList_([0-9A-Z]+)" title="([^"]*)"[^>]*>(.*?)</table>', re.S
)
_SECTION_RE = re.compile(r"<b>([^<(]+)\(\d+家\)</b>")
_STOCK_CODE_RE = re.compile(r"company_basic\.php\?stk_code=([0-9A-Z]+)")

# 細產業資料結構：
# {sub_id: {"name": "濾波器、振盪器", "chain_id": "J000", "chain": "被動元件", "codes": ["2484", ...]}}
SubIndustryMap = Dict[str, Dict]


def _clean_sub_name(title: str) -> str:
    """去掉細產業名稱後的括號說明，例：'電阻器材料(氧化鋁陶瓷基板、導電漿墨)' → '電阻器材料'"""
    name = html.unescape(title).strip()
    return re.split(r"[（(]", name, maxsplit=1)[0].strip() or name


def parse_chain_ids(index_html: str) -> List[str]:
    """從平台首頁解析所有產業鏈代碼（保持出現順序、去重）"""
    seen: List[str] = []
    for chain_id in _CHAIN_LINK_RE.findall(index_html):
        if chain_id not in seen:
            seen.append(chain_id)
    return seen


def parse_chain_page(chain_id: str, page_html: str) -> SubIndustryMap:
    """解析單一產業鏈頁面，回傳該鏈底下所有細產業及其上市櫃成分股"""
    title_match = _PAGE_TITLE_RE.search(page_html)
    chain_name = html.unescape(title_match.group(1)).strip() if title_match else chain_id

    result: SubIndustryMap = {}
    for sub_id, title, body in _COMPANY_LIST_RE.findall(page_html):
        codes: List[str] = []
        # 依「本國上市公司(n家)」等區段切開，只取允許的區段
        parts = _SECTION_RE.split(body)
        # split 結果：[前綴, 區段名1, 內容1, 區段名2, 內容2, ...]
        for i in range(1, len(parts) - 1, 2):
            section, content = parts[i].strip(), parts[i + 1]
            if section not in _ALLOWED_SECTIONS:
                continue
            for code in _STOCK_CODE_RE.findall(content):
                if code not in codes:
                    codes.append(code)
        if codes:
            result[sub_id] = {
                "name": _clean_sub_name(title),
                "chain_id": chain_id,
                "chain": chain_name,
                "codes": codes,
            }
    return result


def _get(url: str) -> str:
    resp = requests.get(url, headers=_HEADERS, timeout=30, verify=False)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return resp.text


def fetch_sub_industries(request_interval: float = 0.3) -> SubIndustryMap:
    """從產業價值鏈平台抓取全部細產業（約 45 個產業鏈頁面）"""
    chain_ids = parse_chain_ids(_get(f"{BASE_URL}/index.php"))
    logger.info(f"產業價值鏈平台：共 {len(chain_ids)} 個產業鏈")

    result: SubIndustryMap = {}
    for chain_id in chain_ids:
        try:
            result.update(parse_chain_page(chain_id, _get(f"{BASE_URL}/introduce.php?ic={chain_id}")))
        except Exception as e:
            logger.warning(f"產業鏈 {chain_id} 抓取失敗: {e}")
        time.sleep(request_interval)

    logger.info(f"共取得 {len(result)} 個細產業")
    return result


def _load_cache(ttl_hours: Optional[float]) -> Optional[SubIndustryMap]:
    """讀取快取；ttl_hours=None 表示忽略過期時間"""
    if not CACHE_FILE.exists():
        return None
    try:
        with open(CACHE_FILE, encoding="utf-8") as f:
            payload = json.load(f)
        cached_at = datetime.fromisoformat(payload["cached_at"])
        if ttl_hours is None or datetime.now() - cached_at < timedelta(hours=ttl_hours):
            return payload["sub_industries"]
    except Exception:
        pass
    return None


def _save_cache(data: SubIndustryMap) -> None:
    try:
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(
                {"cached_at": datetime.now().isoformat(), "sub_industries": data},
                f,
                ensure_ascii=False,
            )
    except Exception as e:
        logger.warning(f"寫入細產業快取失敗: {e}")


def get_sub_industries(use_cache: bool = True, ttl_hours: float = 168) -> SubIndustryMap:
    """取得細產業對照（優先使用快取）"""
    if use_cache:
        cached = _load_cache(ttl_hours)
        if cached is not None:
            return cached

    data = fetch_sub_industries()
    if data:
        _save_cache(data)
    elif CACHE_FILE.exists():
        # 抓取失敗時退回過期快取，避免整個功能失效
        logger.warning("細產業抓取失敗，改用過期快取")
        return _load_cache(ttl_hours=None) or {}
    return data


def build_stock_to_sub_industries(sub_industries: SubIndustryMap) -> Dict[str, List[str]]:
    """反轉對照表：{股票代號: [細產業 id, ...]}"""
    mapping: Dict[str, List[str]] = {}
    for sub_id, info in sub_industries.items():
        for code in info["codes"]:
            mapping.setdefault(code, []).append(sub_id)
    return mapping


def format_sub_industry(info: Dict) -> str:
    """顯示用名稱，例：'被動元件/濾波器、振盪器'"""
    return f"{info['chain']}/{info['name']}"
