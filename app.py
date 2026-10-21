import json
import unicodedata
from pathlib import Path
from flask import Flask, render_template_string, request
from collections import deque
import itertools

CACHE_FILE = Path(__file__).with_name("ufc_lw_fw_fights.json")
CN_MAP_FILE = Path(__file__).with_name("fighter_cn_map.json")

app = Flask(__name__)

# 默认内置对照表兜底
DEFAULT_FIGHTER_CN_MAP = {
    "Jon Jones": "乔恩·琼斯",
    "Alexander Volkanovski": "亚历山大·沃尔卡诺夫斯基",
    "Justin Gaethje": "贾斯汀·加瑟基",
    "Islam Makhachev": "伊斯拉姆·马哈切夫",
    "Charles Oliveira": "查尔斯·奥利维拉",
    "Max Holloway": "马克斯·霍洛威",
    "Israel Adesanya": "伊斯雷尔·阿迪萨亚",
    "Alex Pereira": "亚历克斯·佩雷拉",
    "Kamaru Usman": "卡马鲁·乌斯曼",
    "Leon Edwards": "里昂·爱德华兹",
    "Conor McGregor": "康纳·麦格雷戈",
    "Dustin Poirier": "达斯汀·普里尔",
    "Khabib Nurmagomedov": "哈比布·努尔马戈梅多夫",
    "Sean O'Malley": "肖恩·奥马利",
    "Aljamain Sterling": "阿尔加麦恩·斯特林",
    "Merab Dvalishvili": "梅拉德·德瓦利什维利",
    "Ilia Topuria": "伊利亚·托普里亚",
    "Dricus Du Plessis": "德里库斯·杜·普莱西斯",
    "Tom Aspinall": "汤姆·阿斯皮纳尔",
    "Zhang Weili": "张伟丽",
    "Weili Zhang": "张伟丽",
    "Amanda Nunes": "阿曼达·努涅斯",
    "Valentina Shevchenko": "瓦莲京娜·舍甫琴科",
    "Rose Namajunas": "罗斯·纳马尤纳斯",
    "Deiveson Figueiredo": "戴维森·菲格雷多",
    "Brandon Moreno": "布兰登·莫雷诺",
    "Alexandre Pantoja": "亚历山大·潘托贾",
    "Petr Yan": "彼得·严",
    "Henry Cejudo": "亨利·赛胡多",
    "Cory Sandhagen": "科里·桑德哈根",
    "Arman Tsarukyan": "阿尔曼·萨图基安",
    "Beneil Dariush": "本尼尔·达里尤什",
    "Michael Chandler": "迈克尔·钱德勒",
    "Colby Covington": "科比·卡温顿",
    "Gilbert Burns": "吉尔伯特·伯恩斯",
    "Belal Muhammad": "贝拉尔·穆罕默德",
    "Shavkat Rakhmonov": "沙夫卡特·拉赫莫诺夫",
    "Jack Della Maddalena": "杰克·德拉·马达莱纳",
    "Robert Whittaker": "罗伯特·维泰特",
    "Sean Strickland": "肖恩·斯特里克兰",
    "Paulo Costa": "保罗·科斯塔",
    "Marvin Vettori": "马尔文·韦托里",
    "Jiri Prochazka": "吉里·普罗查兹卡",
    "Jamahal Hill": "贾马哈·希尔",
    "Jan Blachowicz": "扬·拉霍维奇",
    "Aleksandar Rakic": "亚历山大·拉基奇",
    "Magomed Ankalaev": "马戈梅德·安卡拉耶夫",
    "Sergei Pavlovich": "谢尔盖·帕夫洛维奇",
    "Curtis Blaydes": "柯蒂斯·布莱兹",
    "Alexander Volkov": "亚历山大·沃尔科夫",
    "Jairzinho Rozenstruik": "加尔津尼奥·罗森斯特鲁克",
    "Alexa Grasso": "亚历克莎·格拉索",
    "Yan Xiaonan": "闫晓楠",
    "Tatiana Suarez": "塔蒂亚娜·苏亚雷斯",
    "Manon Fiorot": "曼昂·菲奥罗特",
    "Erin Blanchfield": "艾琳·布兰奇菲尔德"
}

# 加载完整的中文映射库（包含别名和出处）
def load_full_cn_map():
    if CN_MAP_FILE.exists():
        try:
            return json.loads(CN_MAP_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return DEFAULT_FIGHTER_CN_MAP

FULL_CN_MAP = load_full_cn_map()

def get_cn_name(en_name):
    """从新版或默认映射中安全获取中文主译名"""
    if not en_name:
        return ""
    if en_name in FULL_CN_MAP:
        info = FULL_CN_MAP[en_name]
        if isinstance(info, dict):
            return info.get("name_cn", en_name)
        return info
    return DEFAULT_FIGHTER_CN_MAP.get(en_name, en_name)

def normalize_text(text):
    """去除西语/法语等重音符号（如将 í 变为 i），并统一转为小写"""
    if not text:
        return ""
    nfkd_form = unicodedata.normalize('NFKD', str(text))
    only_ascii = "".join([c for c in nfkd_form if not unicodedata.combining(c)])
    return only_ascii.lower().strip()

def char_similarity(s1, s2):
    """计算两个中文词的字符重合度比例（用于错别字容错）"""
    if not s1 or not s2:
        return 0.0
    s1_clean = s1.replace("·", "").replace(" ", "").lower()
    s2_clean = s2.replace("·", "").replace(" ", "").lower()
    common_chars = sum(1 for c in s1_clean if c in s2_clean)
    return common_chars / max(len(s1_clean), len(s2_clean))

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
            winner_id, loser_id = first_id, second_id
        elif is_winner(second.get("winner")):
            winner_id, loser_id = second_id, first_id
        else:
            continue

        graph.setdefault(winner_id, set()).add(loser_id)

    return graph, names

def find_fighter_id_fuzzy(name, names):
    """超级模糊匹配：支持重音符消除、多别名、子串匹配以及错别字/音近字容错"""
    typed_raw = name.strip()
    typed_norm = normalize_text(typed_raw)
    if not typed_norm:
        return None

    # 1. 第一轮：精准匹配 / 去重音英文名 / 主译名 / 别名
    for fighter_id, fighter_name in names.items():
        en_norm = normalize_text(fighter_name)
        info = FULL_CN_MAP.get(fighter_name, {})
        
        if isinstance(info, dict):
            cn_main = info.get("name_cn", "").strip().lower()
            aliases = [a.strip().lower() for a in info.get("aliases_cn", []) if isinstance(a, str)]
        else:
            cn_main = str(info).strip().lower()
            aliases = []
        
        all_cn_names = [cn_main] + aliases + ["芽儿", "芽儿罗德里格斯", "亚尔罗德里格斯", "亚尔罗戈里格斯"] if "Yair" in fighter_name else [cn_main] + aliases
        
        if typed_norm == en_norm or typed_raw.lower() in all_cn_names or typed_norm in [normalize_text(a) for a in aliases]:
            return fighter_id

    # 2. 第二轮：包含与子字符串模糊匹配
    for fighter_id, fighter_name in names.items():
        en_norm = normalize_text(fighter_name)
        info = FULL_CN_MAP.get(fighter_name, {})
        
        if isinstance(info, dict):
            cn_main = info.get("name_cn", "").strip().lower()
            aliases = [a.strip().lower() for a in info.get("aliases_cn", []) if isinstance(a, str)]
        else:
            cn_main = str(info).strip().lower()
            aliases = []
            
        all_cn_names = [cn_main] + aliases
        
        if (typed_norm in en_norm) or any(typed_raw.lower() in a for a in all_cn_names if a) or any(typed_norm in normalize_text(a) for a in aliases if a):
            return fighter_id

    # 3. 第三轮：错别字/音近字容错匹配（针对打错字如“亚尔罗戈里格斯” -> “亚伊尔·罗德里格斯”）
    best_match_id = None
    highest_sim = 0.0
    
    for fighter_id, fighter_name in names.items():
        info = FULL_CN_MAP.get(fighter_name, {})
        cn_main = info.get("name_cn", "") if isinstance(info, dict) else str(info)
        aliases = info.get("aliases_cn", []) if isinstance(info, dict) else []
        
        candidates = [cn_main] + aliases
        for cand in candidates:
            if not cand:
                continue
            sim = char_similarity(typed_raw, cand)
            if sim > highest_sim and sim >= 0.55: # 重合度达到 55% 以上即视作同名错别字
                highest_sim = sim
                best_match_id = fighter_id

    if best_match_id:
        return best_match_id

    return None

def find_shortest_paths(graph, start_id, target_id, max_depth=10, max_paths=500):
    """
    带内存安全阀的 BFS 算法：
    1. 限制最大搜索步数 max_depth=10（防止跨量级死循环或过度爆搜索Tree）
    2. 限制最多保存的路径条数 max_paths=500（防止几万条路径塞爆 RAM）
    """
    if start_id == target_id:
        return [[start_id]]
    
    paths = []
    queue = deque([[start_id]])
    found_length = None
    visited_at_length = {} # 记录节点被首次/最短访问时的步数
    
    while queue:
        # 内存安全阀 1：如果找到的路径总数达到了安全上限，提前终止，防止 OOM
        if len(paths) >= max_paths:
            break
            
        path = queue.popleft()
        current = path[-1]
        
        # 内存安全阀 2：限制最大搜索步数
        if len(path) > max_depth:
            break
        
        if found_length is not None and len(path) > found_length:
            break
            
        if current == target_id:
            if found_length is None:
                found_length = len(path)
            if len(path) == found_length:
                paths.append(path)
            continue
            
        for neighbor in graph.get(current, set()):
            if neighbor not in path:
                new_path = path + [neighbor]
                new_length = len(new_path)
                
                # 剪枝优化：如果某个节点在更短或相同步数下已经被海量遍历过，限制重复入队分支
                if neighbor in visited_at_length and visited_at_length[neighbor] < new_length - 1:
                    continue
                    
                visited_at_length[neighbor] = new_length - 1
                
                if found_length is None or new_length <= found_length:
                    queue.append(new_path)
                    
    return paths

def find_paths_through_waypoints(graph, node_ids):
    """
    核心途径点逻辑：将 A > B > C 拆解为段落 (A>B, B>C)，
    分别求各段最短路径，然后组合并剔除重复选手。
    """
    if len(node_ids) < 2:
        return []
        
    segment_paths = []
    for i in range(len(node_ids) - 1):
        s = node_ids[i]
        t = node_ids[i+1]
        paths = find_shortest_paths(graph, s, t)
        if not paths:
            return [] # 某一环节不通，整个链条断裂
        segment_paths.append(paths)
        
    current_combinations = segment_paths[0]
    for next_segment in segment_paths[1:]:
        new_combinations = []
        for p1 in current_combinations:
            for p2 in next_segment:
                combined = p1[:-1] + p2
                if len(combined) == len(set(combined)):
                    new_combinations.append(combined)
        current_combinations = new_combinations
        if not current_combinations:
            break
            
    return current_combinations

# 启动加载数据
if not CACHE_FILE.exists():
    raise FileNotFoundError("找不到 ufc_lw_fw_fights.json，请先运行 mma_test.py！")

fights = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
graph, names = build_graph(fights)
fighter_names = sorted(names.values())


PAGE = """
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>UFC 选手叠盒子计算器 | UFC MMA Math Calculator</title>
  <style>
    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100vh;
      font-family: Arial, "Microsoft YaHei", sans-serif;
      background: #0d0f12;
      color: #f5f5f5;
    }
    main {
      width: min(980px, calc(100% - 32px));
      margin: 0 auto;
      padding: 48px 0;
    }
    .tag {
      color: #ff4d37;
      font-size: 13px;
      font-weight: bold;
      letter-spacing: 2px;
    }
    h1 {
      margin: 12px 0;
      font-size: clamp(26px, 5vw, 48px);
    }
    .intro { color: #aeb5bf; line-height: 1.7; font-size: 15px; }
    .panel {
      margin-top: 28px;
      padding: 28px;
      border: 1px solid #303640;
      border-radius: 18px;
      background: #161a20;
      box-shadow: 0 8px 24px rgba(0,0,0,0.4);
    }
    .form-group {
      display: grid;
      grid-template-columns: 1fr auto 1fr auto;
      gap: 12px;
      align-items: center;
    }
    .waypoint-box {
      margin-top: 14px;
    }
    input, button {
      border: 0;
      border-radius: 10px;
      font-size: 16px;
      padding: 14px 18px;
    }
    input { 
      background: #272d36; 
      color: white; 
      outline: none; 
      width: 100%; 
      font-size: 16px;
    }
    input:focus { border: 1px solid #ff4d37; }
    
    .swap-btn {
      background: #272d36;
      color: #aeb5bf;
      border: 1px solid #3d4654;
      cursor: pointer;
      padding: 14px 16px;
      border-radius: 10px;
      font-weight: bold;
      transition: all 0.2s;
    }
    .swap-btn:hover {
      background: #ff4d37;
      color: white;
      border-color: #ff4d37;
    }

    button[type="submit"] {
      cursor: pointer;
      background: #ff4d37;
      color: white;
      font-weight: bold;
      white-space: nowrap;
    }
    button[type="submit"]:hover { background: #ff3219; }

    .notice, .result {
      margin-top: 24px;
      padding: 18px;
      border-radius: 12px;
    }
    .notice { background: #33211e; color: #ffb7a9; border: 1px solid #5c2c26; }
    .result { background: #202731; border: 1px solid #2e3846; }
    
    .path {
      padding: 12px 0;
      border-bottom: 1px solid #343b45;
      color: #e9edf3;
      line-height: 1.6;
      font-size: 15px;
    }
    .path:last-child { border-bottom: 0; }
    .muted { color: #9da6b2; font-size: 13px; }

    details {
      margin-top: 15px;
      background: #191e26;
      border: 1px solid #2e3846;
      border-radius: 10px;
      padding: 12px 16px;
    }
    summary {
      cursor: pointer;
      color: #ff4d37;
      font-weight: bold;
      outline: none;
    }
    summary:hover { color: #ff6a55; }

    @media (max-width: 768px) {
      .form-group { grid-template-columns: 1fr; }
      .swap-btn { width: 100%; }
    }
  </style>
</head>
<body>
  <main>
    <div class="tag">UFC MMA MATH CALCULATOR / 叠盒子计算器</div>
    <h1>UFC 选手叠盒子计算器</h1>
    <p class="intro">
      输入两名选手，默认秒级计算<strong>最短胜负链条</strong>。<br>
      Query shortest transitive logic chains between Fighter A and Z instantly.<br>
      支持通过途径点（如 B 或 B > C）组合更长的进阶逻辑。
    </p>

    <section class="panel">
      <form method="post" id="calcForm">
        <div class="form-group">
          <!-- 选手 A -->
          <input list="fighters" name="start" id="startInput" placeholder="选手 A (如 Volkanovski / 沃尔卡诺夫斯基)"
                 value="{{ start }}" required>
          
          <!-- 交换按钮 -->
          <button type="button" class="swap-btn" onclick="swapFighters()" title="互换 A 和 Z / Swap">⇄ 互换 / Swap</button>

          <!-- 选手 Z -->
          <input list="fighters" name="target" id="targetInput" placeholder="选手 Z (如 Gaethje / 加瑟基)"
                 value="{{ target }}" required>

          <!-- 提交按钮 -->
          <button type="submit">开始计算<br><span style="font-size: 11px; font-weight: normal;">Calculate</span></button>
        </div>

        <!-- 途径点输入框 -->
        <div class="waypoint-box">
          <input type="text" name="waypoints" placeholder="途径点（可选，如输入 C 或 C > F，支持中英文链条） / Intermediate waypoints (optional)"
                 value="{{ waypoints }}">
        </div>
      </form>

      <datalist id="fighters">
        {% for fighter in fighter_names %}
        <option value="{{ fighter }}">
        {% endfor %}
      </datalist>

      {% if error %}
      <div class="notice">{{ error }}</div>
      {% endif %}

      {% if matched_start and matched_target %}
      <div style="margin-top: 15px; color: #8892b0; font-size: 14px;">
        🎯 匹配识别 / Match: <strong>{{ matched_start }}</strong> vs <strong>{{ matched_target }}</strong>
        {% if matched_waypoints_str %}
        <br>📍 途径点 / Waypoints: <span style="color: #ff9d00;">{{ matched_waypoints_str }}</span>
        {% endif %}
      </div>
      {% endif %}

      {% if paths is not none %}
      <div class="result">
        <strong style="font-size: 17px;">
          找到 {{ total_count }} 条路径 / Found {{ total_count }} paths:
        </strong>
        <div style="margin-top: 12px;"></div>

        {% if paths %}
          <div style="font-size: 13px; color: #ff9d00; margin-bottom: 8px;">
            🔥 默认展示较短路径（≤{{ default_display_steps }}步 / Shortest paths displayed by default）：
          </div>
          {% for p_item in default_paths %}
          <div class="path">
            <strong>#{{ p_item.index }}</strong> [{{ p_item.steps }}步/Steps]: 
            {{ p_item.formatted_html|safe }}
          </div>
          {% endfor %}

          {% if longer_paths %}
          <details>
            <summary>📂 点击展开查看更长的路径 ({{ longer_paths|length }} 条 / Click to expand longer paths)</summary>
            <div style="margin-top: 12px;">
              {% for p_item in longer_paths %}
              <div class="path">
                <strong>#{{ p_item.index }}</strong> [{{ p_item.steps }}步/Steps]: 
                {{ p_item.formatted_html|safe }}
              </div>
              {% endfor %}
            </div>
          </details>
          {% endif %}

        {% else %}
          <p class="muted" style="margin: 4px 0 0 0;">未能在当前条件下找到符合要求的路径。</p>
          <p class="muted" style="margin: 4px 0 0 0; font-size: 13px;">No path found under current condition.</p>
          
          {% if rev_paths %}
          <div style="margin-top: 15px; padding-top: 12px; border-top: 1px dashed #444;">
            <p style="color: #ff9d00;">💡 提示 / Tip: 顺向没找到，但找到了 <strong>{{ matched_target }}</strong> 反向叠盒子赢 <strong>{{ matched_start }}</strong> 的路径 / Reverse paths found:</p>
            {% for r_item in rev_paths %}
            <div class="path" style="color: #ccc;">
              <strong>#{{ r_item.index }}</strong> [{{ r_item.steps }}步]: {{ r_item.formatted_html|safe }}
            </div>
            {% endfor %}
          </div>
          {% endif %}
        {% endif %}
      </div>
      {% endif %}
    </section>
  </main>

  <script>
    function swapFighters() {
      const startInput = document.getElementById('startInput');
      const targetInput = document.getElementById('targetInput');
      const temp = startInput.value;
      startInput.value = targetInput.value;
      targetInput.value = temp;
    }
  </script>
</body>
</html>
"""


@app.route("/", methods=["GET", "POST"])
def home():
    start = ""
    target = ""
    waypoints = ""
    error = ""
    paths = None
    rev_paths = None
    matched_start = ""
    matched_target = ""
    matched_waypoints_str = ""
    default_paths = []
    longer_paths = []
    total_count = 0
    default_display_steps = 4

    display_fighter_names = []
    for en_name in fighter_names:
        cn = get_cn_name(en_name)
        if cn and cn != en_name:
            display_fighter_names.append(f"{en_name} ({cn})")
        else:
            display_fighter_names.append(en_name)

    if request.method == "POST":
        start = request.form.get("start", "")
        target = request.form.get("target", "")
        waypoints = request.form.get("waypoints", "").strip()

        clean_start = start.split("(")[0].strip()
        clean_target = target.split("(")[0].strip()

        start_id = find_fighter_id_fuzzy(clean_start, names)
        target_id = find_fighter_id_fuzzy(clean_target, names)

        if start_id is None or target_id is None:
            error = "未匹配到选手，请输入正确的名字、姓氏或别名（如 Volkanovski 或 沃尔卡诺夫斯基）。 / Fighter not found."
        else:
            en_start = names[start_id]
            en_target = names[target_id]
            matched_start = f"{en_start} ({get_cn_name(en_start)})"
            matched_target = f"{en_target} ({get_cn_name(en_target)})"

            waypoint_ids = []
            waypoint_names_matched = []
            if waypoints:
                separators = [">", "→", ",", "，", " "]
                parts = [waypoints]
                for sep in separators:
                    new_parts = []
                    for p in parts:
                        new_parts.extend(p.split(sep))
                    parts = new_parts
                
                for part in parts:
                    p_clean = part.split("(")[0].strip()
                    if p_clean:
                        fid = find_fighter_id_fuzzy(p_clean, names)
                        if fid and fid not in waypoint_ids and fid != start_id and fid != target_id:
                            waypoint_ids.append(fid)
                            en_w = names[fid]
                            waypoint_names_matched.append(f"{en_w} ({get_cn_name(en_w)})")

            if waypoint_names_matched:
                matched_waypoints_str = " → ".join(waypoint_names_matched)

            full_chain_ids = [start_id] + waypoint_ids + [target_id]

            if len(waypoint_ids) == 0:
                raw_paths = find_shortest_paths(graph, start_id, target_id)
            else:
                raw_paths = find_paths_through_waypoints(graph, full_chain_ids)

            def format_path_items(path_ids):
                items_html = []
                for fid in path_ids:
                    en = names[fid]
                    cn = get_cn_name(en)
                    if cn and cn != en:
                        items_html.append(f"{en} <span class='muted'>({cn})</span>")
                    else:
                        items_html.append(en)
                return " → ".join(items_html)

            formatted_paths = []
            for path in raw_paths:
                step_count = len(path) - 1
                formatted_paths.append({
                    "path_ids": path,
                    "steps": step_count,
                    "formatted_html": format_path_items(path)
                })

            formatted_paths.sort(key=lambda x: x["steps"])
            total_count = len(formatted_paths)
            paths = formatted_paths

            if paths:
                min_steps = paths[0]["steps"]
                effective_default_limit = max(default_display_steps, min_steps)

                for idx, p in enumerate(paths, 1):
                    p["index"] = idx
                    if p["steps"] <= effective_default_limit:
                        default_paths.append(p)
                    else:
                        longer_paths.append(p)

            if not paths and not waypoint_ids:
                raw_rev_paths = find_shortest_paths(graph, target_id, start_id)
                rev_formatted = []
                for idx, path in enumerate(raw_rev_paths[:10], 1):
                    rev_formatted.append({
                        "index": idx,
                        "steps": len(path) - 1,
                        "formatted_html": format_path_items(path)
                    })
                rev_paths = rev_formatted

    return render_template_string(
        PAGE,
        fighter_names=display_fighter_names,
        max_steps=30,
        start=start,
        target=target,
        waypoints=waypoints,
        error=error,
        paths=paths,
        rev_paths=rev_paths,
        default_paths=default_paths,
        longer_paths=longer_paths,
        total_count=total_count,
        default_display_steps=default_display_steps,
        matched_start=matched_start,
        matched_target=matched_target,
        matched_waypoints_str=matched_waypoints_str,
    )


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
