import json
from pathlib import Path
import time
import requests

API_BASE = "https://v1.mma.api-sports.io"
CACHE_FILE = Path("ufc_lw_fw_fights.json")

MAX_STEPS = 5
# 扩充为 API-Sports 免费档支持的 18 个标准量级，涵盖更丰富的选手
CATEGORIES = [
    "Lightweight", "Featherweight", "Welterweight", "Middleweight", 
    "Light Heavyweight", "Heavyweight", "Bantamweight", "Flyweight",
    "Women's Strawweight", "Women's Flyweight", "Women's Bantamweight", "Women's Featherweight",
    "Middleweight", "Welterweight", "Lightweight", "Featherweight", "Bantamweight", "Flyweight"
]
# 去重防止重复请求
CATEGORIES = [
    "Lightweight", "Featherweight", "Welterweight", "Middleweight", 
    "Light Heavyweight", "Heavyweight", "Bantamweight", "Flyweight",
    "Women's Strawweight", "Women's Flyweight", "Women's Bantamweight", "Women's Featherweight"
]
FREE_YEARS = [2021, 2022, 2023, 2024]


def get_api_data(api_key, endpoint, parameters):
    response = requests.get(
        f"{API_BASE}{endpoint}",
        headers={"x-apisports-key": api_key},
        params=parameters,
        timeout=30,
    )

    # 检查频率限制头信息
    remaining = response.headers.get("X-RateLimit-Remaining")
    if remaining is not None:
        print(f"  [API 提示] 当前分钟剩余额度：{remaining}")

    try:
        data = response.json()
    except ValueError:
        raise RuntimeError(f"API 没有返回正确数据，状态码：{response.status_code}")

    if response.status_code != 200:
        raise RuntimeError(f"API 请求失败：{data}")

    if data.get("errors"):
        # 如果遇到限流，稍微暂停一下
        if "rate limit" in str(data['errors']).lower():
            print("  [警告] 触发频率限制，等待 60 秒...")
            time.sleep(60)
            return get_api_data(api_key, endpoint, parameters)
        raise RuntimeError(f"API 报错：{data['errors']}")

    return data


def is_ufc_fight(fight):
    # 确保是 UFC 的比赛
    slug = str(fight.get("slug", "")).upper()
    league = str(fight.get("league", {}).get("name", "")).upper()
    return "UFC" in slug or "UFC" in league


def download_fights(api_key):
    print("开始从 API-Sports 下载 2022-2024 年各量级 UFC 比赛...")
    fights_by_id = {}

    for year in FREE_YEARS:
        for category in CATEGORIES:
            print(f"正在下载：年份 {year} | 量级 {category}")
            try:
                data = get_api_data(
                    api_key,
                    "/fights",
                    {
                        "season": year,
                        "category": category,
                    },
                )

                count = 0
                for fight in data.get("response", []):
                    fight_id = fight.get("id")
                    if fight_id is not None and is_ufc_fight(fight):
                        fights_by_id[fight_id] = fight
                        count += 1
                print(f"  -> 成功收录 {count} 场 UFC 比赛")
                
                # 每次请求后稍微停顿，避免触发每分钟 10 次的限制
                time.sleep(6.5)
            except Exception as e:
                print(f"  -> 下载出错跳过: {e}")

    return list(fights_by_id.values())


def is_winner(value):
    return value is True or str(value).lower() == "true"


def build_graph(fights):
    graph = {}
    names = {}

    for fight in fights:
        fighters = fight.get("fighters", {})
        first = fighters.get("first", {})
        second = fighters.get("second", {})

        first_id = first.get("id")
        second_id = second.get("id")
        first_name = first.get("name")
        second_name = second.get("name")

        if not all([first_id, second_id, first_name, second_name]):
            continue

        names[first_id] = first_name
        names[second_id] = second_name

        if is_winner(first.get("winner")):
            winner_id = first_id
            loser_id = second_id
        elif is_winner(second.get("winner")):
            winner_id = second_id
            loser_id = first_id
        else:
            continue

        graph.setdefault(winner_id, set()).add(loser_id)

    return graph, names


def load_fights():
    if CACHE_FILE.exists():
        use_cache = input("发现本地比赛数据缓存。是否直接使用而不消耗 API？(y/n，默认 y)：").strip().lower()
        if use_cache in ("", "y", "yes"):
            try:
                fights = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
                print(f"已从本机成功读取 {len(fights)} 场比赛。")
                return fights
            except (json.JSONDecodeError, OSError):
                print("本地数据文件损坏，将重新下载。")

    api_key = input("请输入你的 API-Sports Key：").strip()
    if not api_key:
        raise RuntimeError("没有输入 API Key。")

    fights = download_fights(api_key)
    if not fights:
        raise RuntimeError("没有下载到符合范围的 UFC 比赛。")

    CACHE_FILE.write_text(
        json.dumps(fights, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"已成功保存 {len(fights)} 场比赛到本地文件 {CACHE_FILE}。")
    return fights


def main():
    print("=== UFC 叠盒子计算器数据准备程序 ===")
    try:
        fights = load_fights()
    except RuntimeError as error:
        print(f"\n程序停止：{error}")
        return

    graph, names = build_graph(fights)
    edge_count = sum(len(losers) for losers in graph.values())
    print(f"\n数据库就绪！包含 {len(names)} 名选手、{edge_count} 条胜负关系。")
    print("现在你可以运行 app.py 启动网页端了。")


if __name__ == "__main__":
    main()