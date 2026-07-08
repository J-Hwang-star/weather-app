"""
SK 하이닉스 최신 뉴스 Top 3 검색 스크립트 (네이버 뉴스 API)

사용 전 준비:
1. https://developers.naver.com/apps/#/register 에서 애플리케이션 등록
2. Client ID / Client Secret 발급
3. 환경 변수로 등록 (아래 방법 중 택 1)
   - Windows:  setx NAVER_CLIENT_ID "YOUR_ID"
               setx NAVER_CLIENT_SECRET "YOUR_SECRET"
   - 또는 스크립트와 같은 폴더에 .env 파일 생성:
       NAVER_CLIENT_ID=whitekar
       NAVER_CLIENT_SECRET=YOUR_SECRET

실행:
    python naver_news_sk_hynix.py
"""

import os
import sys
import json
import urllib.request
import urllib.parse
import urllib.error

# .env 파일이 있으면 로드 (python-dotenv 미설치 환경 대응용 간단 버전)
def load_env_file():
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, value = line.split("=", 1)
                    key, value = key.strip(), value.strip().strip('"').strip("'")
                    if key not in os.environ:
                        os.environ[key] = value

load_env_file()

CLIENT_ID = os.environ.get("NAVER_CLIENT_ID", "")
CLIENT_SECRET = os.environ.get("NAVER_CLIENT_SECRET", "")

QUERY = "SK 하이닉스"
DISPLAY = 3      # Top 3
SORT = "date"    # 최신순(date) / 정확도순(sim)


def search_news():
    if not CLIENT_ID or not CLIENT_SECRET:
        print("[오류] 네이버 API 자격 증명이 없습니다.")
        print("환경 변수 NAVER_CLIENT_ID, NAVER_CLIENT_SECRET를 설정하세요.")
        print("또는 스크립트와 같은 폴더에 .env 파일을 작성하세요.")
        sys.exit(1)

    url = "https://openapi.naver.com/v1/search/news.json"
    params = urllib.parse.urlencode(
        {
            "query": QUERY,
            "display": DISPLAY,
            "start": 1,
            "sort": SORT,
        }
    )
    full_url = f"{url}?{params}"

    req = urllib.request.Request(full_url)
    req.add_header("X-Naver-Client-Id", CLIENT_ID)
    req.add_header("X-Naver-Client-Secret", CLIENT_SECRET)

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        print(f"[HTTP 오류] {e.code} {e.reason}")
        print(body)
        sys.exit(1)
    except urllib.error.URLError as e:
        print(f"[네트워크 오류] {e.reason}")
        sys.exit(1)

    items = data.get("items", [])
    if not items:
        print("검색 결과가 없습니다.")
        return

    print(f"[{QUERY}] 최신 뉴스 Top {len(items)}\n" + "=" * 60)
    for i, item in enumerate(items, 1):
        # 제목/요약에 HTML 엔티티가 포함되어 있어 간단히 디코딩
        def clean(s):
            return (
                s.replace("&quot;", '"')
                .replace("&#39;", "'")
                .replace("&lt;", "<")
                .replace("&gt;", ">")
                .replace("&amp;", "&")
            )
        title = clean(item.get("title", ""))
        link = item.get("link", "")
        pub = item.get("pubDate", "")
        desc = clean(item.get("description", ""))
        print(f"[{i}] {title}")
        print(f"    언론/날짜: {pub}")
        print(f"    링크: {link}")
        print(f"    요약: {desc}")
        print()


if __name__ == "__main__":
    search_news()
