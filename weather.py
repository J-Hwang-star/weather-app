"""간단한 날씨 앱 (Open-Meteo, API 키 불필요)

사용법:
    python weather.py              # 기본: 서울
    python weather.py 부산          # 도시명으로 검색
"""

import sys
import json
import urllib.request
import urllib.parse


def get_coords(city):
    url = "https://geocoding-api.open-meteo.com/v1/search?" + urllib.parse.urlencode(
        {"name": city, "count": 1, "language": "ko"}
    )
    with urllib.request.urlopen(url, timeout=10) as r:
        data = json.loads(r.read())
    if not data.get("results"):
        return None
    p = data["results"][0]
    return p["latitude"], p["longitude"], p.get("name", city)


def get_weather(lat, lon):
    url = (
        f"https://api.open-meteo.com/v1/forecast?"
        f"latitude={lat}&longitude={lon}"
        f"&current=temperature_2m,relative_humidity_2m,apparent_temperature,"
        f"weather_code,wind_speed_10m,wind_direction_10m,precipitation"
        f"&hourly=weather_code,temperature_2m,relative_humidity_2m,"
        f"precipitation_probability,precipitation,wind_direction_10m"
        f"&daily=weather_code,temperature_2m_max,temperature_2m_min,"
        f"sunrise,sunset,precipitation_probability_max"
        f"&timezone=Asia/Seoul&forecast_days=11"
    )
    with urllib.request.urlopen(url, timeout=10) as r:
        return json.loads(r.read())


# WMO weather_code -> 한국어 설명
WMO = {
    0: "맑음", 1: "대체로 맑음", 2: "부분적 흐림", 3: "흐림",
    45: "안개", 48: "결빙 안개",
    51: "약한 이슬비", 53: "이슬비", 55: "강한 이슬비",
    61: "약한 비", 63: "비", 65: "강한 비",
    71: "약한 눈", 73: "눈", 75: "강한 눈",
    80: "약한 소나기", 81: "소나기", 82: "강한 소나기",
    95: "천둥번개", 96: "천둥번개+우박", 99: "심한 천둥번개+우박",
}


CITY_MAP = {
    "서울": "Seoul", "부산": "Busan", "대구": "Daegu", "인천": "Incheon",
    "광주": "Gwangju", "대전": "Daejeon", "울산": "Ulsan", "수원": "Suwon",
    "제주": "Jeju", "청주": "Cheongju", "전주": "Jeonju",
}

WEEKDAYS = ["월", "화", "수", "목", "금", "토", "일"]

# 각도 -> 한글 8방위 (불어오는 방향 기준)
def wind_dir(deg):
    dirs = ["북", "북동", "동", "남동", "남", "남서", "서", "북서"]
    return dirs[int((deg + 22.5) // 45) % 8]


# 화살표: 불어가는 방향(불어오는 반대) 가리킴 — 북풍=↓, 동풍=←
def wind_arrow(deg):
    arrows = ["↓", "↙", "←", "↖", "↑", "↗", "→", "↘"]
    return arrows[int(((deg + 180) % 360 + 22.5) // 45) % 8]


def fmt_time(iso):
    # ISO -> HH:MM
    return iso[11:16]


def fmt_date(iso):
    # ISO -> M/D (요일)
    from datetime import date
    y, m, d = map(int, iso[:10].split("-"))
    return f"{m}/{d} ({WEEKDAYS[date(y, m, d).weekday()]})"


def main():
    arg = " ".join(sys.argv[1:]).strip() if len(sys.argv) > 1 else "서울"
    # 한국어 도시명 -> 영문 매핑, 없으면 그대로 Geocoding API에 전달
    city = CITY_MAP.get(arg, arg)
    coords = get_coords(city)
    if not coords:
        print(f"'{city}' 도시를 찾을 수 없습니다.")
        return
    lat, lon, name = coords
    w = get_weather(lat, lon)
    c = w["current"]
    code = c["weather_code"]
    desc = WMO.get(code, f"코드 {code}")

    print(f"=== {name} 현재 날씨 ===")
    print(f"기온: {c['temperature_2m']}°C (체감 {c['apparent_temperature']}°C)")
    print(f"날씨: {desc}")
    print(f"습도: {c['relative_humidity_2m']}%")
    print(f"풍속: {c['wind_speed_10m']} km/h")
    wd = c.get("wind_direction_10m")
    if wd is not None:
        print(f"풍향: {wind_arrow(wd)} {wind_dir(wd)} ({int(wd)}°)")
    print(f"강수량: {c.get('precipitation', 0)} mm")

    # 오늘 일출/일몰
    d = w["daily"]
    print(f"일출: {fmt_time(d['sunrise'][0])} / 일몰: {fmt_time(d['sunset'][0])}")

    # 시간별 예보 (앞으로 24시간)
    print("\n=== 시간별 예보 (24시간) ===")
    hourly = w["hourly"]
    # 현재 시간 이후부터
    now_t = c["time"]
    started = False
    count = 0
    for i, t in enumerate(hourly["time"]):
        if t < now_t:
            continue
        if not started:
            label = "지금"
            started = True
        else:
            label = t[11:16]
        h_desc = WMO.get(hourly["weather_code"][i], "-")
        rain = hourly["precipitation_probability"][i] if "precipitation_probability" in hourly else 0
        precip = hourly["precipitation"][i] if "precipitation" in hourly else None
        hum = hourly["relative_humidity_2m"][i] if "relative_humidity_2m" in hourly else None
        wd = hourly["wind_direction_10m"][i] if "wind_direction_10m" in hourly else None
        line = f"  {label:>5} | {hourly['temperature_2m'][i]:>5.1f}°C | 강수 {rain:>2}%"
        if precip is not None:
            line += f" | {precip}mm"
        if hum is not None:
            line += f" | 습도 {hum}%"
        if wd is not None:
            line += f" | {wind_arrow(wd)} {wind_dir(wd)}"
        line += f" | {h_desc}"
        print(line)
        count += 1
        if count >= 24:
            break

    # 10일 예보 (내일부터)
    print("\n=== 10일 예보 ===")
    for i in range(1, 11):
        t = d["time"][i]
        d_desc = WMO.get(d["weather_code"][i], "-")
        rain = d["precipitation_probability_max"][i] if "precipitation_probability_max" in d else 0
        print(f"  {fmt_date(t)} | {d['temperature_2m_max'][i]:>5.1f}/{d['temperature_2m_min'][i]:>4.1f}°C | 강수 {rain:>2}% | {d_desc}")


if __name__ == "__main__":
    main()
