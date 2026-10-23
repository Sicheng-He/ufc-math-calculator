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

def find_shortest_paths(graph, start_id, target_id, max_depth=30, max_paths=500):
    """
    超远深度 (最长 30 步) + 内存绝对安全阀的 BFS 算法
    """
    if start_id == target_id:
        return [[start_id]]
    
    paths = []
    queue = deque([[start_id]])
    found_length = None
    
    # 记录每个节点在被访问时对应的最短步数，防止同一个节点被重复拓展无限次
    visited_min_depth = {start_id: 1}
    
    # 每一层扩展的数量限制（防止某一层分支太多爆 RAM）
    depth_counts = {}

    while queue:
        if len(paths) >= max_paths:
            break
            
        path = queue.popleft()
        current = path[-1]
        curr_depth = len(path)
        
        # 允许最大 30 步深度
        if curr_depth > max_depth:
            break
            
        if found_length is not None and curr_depth > found_length:
            break
            
        if current == target_id:
            if found_length is None:
                found_length = curr_depth
            if curr_depth == found_length:
                paths.append(path)
            continue
            
        # 限制单层扩展节点数上限，防止爆炸
        depth_counts[curr_depth] = depth_counts.get(curr_depth, 0) + 1
        if depth_counts[curr_depth] > 3000:
            continue

        for neighbor in graph.get(current, set()):
            if neighbor not in path:
                new_depth = curr_depth + 1
                
                # 如果这个节点已经被更短或相同步数的路径访问过，不再重复扩展
                if neighbor in visited_min_depth and visited_min_depth[neighbor] < new_depth:
                    continue
                
                visited_min_depth[neighbor] = new_depth
                
                if found_length is None or new_depth <= found_length:
                    queue.append(path + [neighbor])
                    
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
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>UFC 选手叠盒子计算器 / UFC MMA Math Calculator</title>
    <!-- Tailwind CSS -->
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        .lang-en { display: none; }
    </style>
</head>
<body class="bg-slate-950 text-slate-100 min-h-screen flex flex-col justify-between selection:bg-red-600 selection:text-white">

    <!-- 右上角切换语言按钮 -->
    <div class="absolute top-4 right-4 z-50">
        <button type="button" onclick="toggleLanguage()" id="langBtn" class="px-3 py-1.5 text-xs font-semibold bg-slate-900 border border-slate-700 rounded-lg hover:bg-slate-800 transition text-slate-300 shadow-sm">
            🌐 English / 中文
        </button>
    </div>

    <div class="max-w-3xl mx-auto px-4 py-12 w-full flex-grow">
        
        <!-- 头部标题：严格按要求只有两行大字 -->
        <header class="text-center mb-8">
            <h1 class="text-3xl sm:text-4xl font-extrabold tracking-tight text-white mb-2">
                <span class="lang-zh">UFC 选手叠盒子计算器</span>
                <span class="lang-en">UFC MMA Math Calculator</span>
            </h1>
            <p class="text-lg sm:text-xl font-medium text-red-500">
                <span class="lang-zh">UFC Fighter Transitive Math Calculator</span>
                <span class="lang-en">UFC Fighter Transitive Math Calculator</span>
            </p>
        </header>

        <!-- 项目描述区域 -->
        <section class="bg-slate-900/80 border border-slate-800/80 rounded-2xl p-6 mb-8 shadow-xl backdrop-blur-sm text-sm sm:text-base leading-relaxed text-slate-300">
            <div class="lang-zh space-y-4">
                <p>叠盒子就是通过不断连接“谁赢过谁”，把两名选手联系起来。</p>
                <div class="p-3 bg-slate-950/60 rounded-xl border border-slate-800/60 font-mono text-xs sm:text-sm text-red-400 overflow-x-auto whitespace-nowrap">
                    李景亮 → 圣地亚哥·彭兹尼比奥 → 尼尔·马格尼 → 凯尔文·盖斯特鲁姆 → 迈克尔·比斯平 → 马特·哈米尔 → 乔恩·琼斯 → 斯蒂佩·米欧奇 → 弗朗西斯·纳干诺
                </div>
                <p>每一名选手都曾击败链条中的下一名选手。通过不断连接真实比赛的胜负，我们可以找到几乎任意两名 UFC 选手之间的联系，甚至连接不同量级、不同年代的选手。</p>
            </div>

            <div class="lang-en space-y-4">
                <p>Stacking connects two fighters by linking together “who beat whom.”</p>
                <div class="p-3 bg-slate-950/60 rounded-xl border border-slate-800/60 font-mono text-xs sm:text-sm text-red-400 overflow-x-auto whitespace-nowrap">
                    Li Jingliang → Santiago Ponzinibbio → Neil Magny → Kelvin Gastelum → Michael Bisping → Matt Hamill → Jon Jones → Stipe Miocic → Francis Ngannou
                </div>
                <p>Each fighter defeated the next fighter in the chain. By connecting real fight results, we can find connections between almost any two UFC fighters, even across different weight classes and generations.</p>
            </div>
        </section>

        <!-- 表单计算与输出区 -->
        <main class="bg-slate-900/80 border border-slate-800/80 rounded-2xl p-6 sm:p-8 shadow-xl backdrop-blur-sm">
            <form method="POST" action="/" class="space-y-6">
                <div class="grid grid-cols-1 md:grid-cols-11 gap-4 items-center">
                    <!-- 选手 A -->
                    <div class="md:col-span-5 space-y-2">
                        <label for="startInput" class="block text-xs font-bold uppercase tracking-wider text-slate-400">
                            <span class="lang-zh">起点选手 (Fighter A)</span>
                            <span class="lang-en">Starting Fighter (A)</span>
                        </label>
                        <input list="fighters" name="start" id="startInput" required value="{{ start }}"
                            placeholder="例如：Max Holloway / 霍洛威" 
                            class="w-full bg-slate-950 border border-slate-700 rounded-xl px-4 py-3 text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-red-600 focus:border-transparent transition">
                    </div>

                    <!-- 互换按钮 -->
                    <div class="md:col-span-1 flex justify-center pt-2 md:pt-6">
                        <button type="button" onclick="swapFighters()" title="Swap / 互换" class="p-3 bg-slate-800 hover:bg-slate-700 border border-slate-700 rounded-full text-slate-300 hover:text-white transition shadow-sm">
                            ⇄
                        </button>
                    </div>

                    <!-- 选手 Z -->
                    <div class="md:col-span-5 space-y-2">
                        <label for="targetInput" class="block text-xs font-bold uppercase tracking-wider text-slate-400">
                            <span class="lang-zh">终点选手 (Fighter Z)</span>
                            <span class="lang-en">Target Fighter (Z)</span>
                        </label>
                        <input list="fighters" name="target" id="targetInput" required value="{{ target }}"
                            placeholder="例如：Islam Makhachev / 马哈切夫" 
                            class="w-full bg-slate-950 border border-slate-700 rounded-xl px-4 py-3 text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-red-600 focus:border-transparent transition">
                    </div>
                </div>

                <!-- 途径点 -->
                <div class="space-y-2">
                    <label for="waypoints" class="block text-xs font-bold uppercase tracking-wider text-slate-400">
                        <span class="lang-zh">途径点（可选）</span>
                        <span class="lang-en">Intermediate Waypoints (Optional)</span>
                    </label>
                    <input type="text" id="waypoints" name="waypoints" value="{{ waypoints }}"
                        placeholder="例如：C 或 C > F" 
                        class="w-full bg-slate-950 border border-slate-700 rounded-xl px-4 py-3 text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-red-600 focus:border-transparent transition">
                </div>

                <!-- 提交按钮 -->
                <button type="submit" class="w-full py-4 bg-red-600 hover:bg-red-700 text-white font-bold rounded-xl shadow-lg shadow-red-600/20 transition duration-200 text-center text-base tracking-wide">
                    <span class="lang-zh">开始计算 / Calculate</span>
                    <span class="lang-en">Calculate / 开始计算</span>
                </button>
            </form>

            <datalist id="fighters">
                {% for fighter in fighter_names %}
                <option value="{{ fighter }}">
                {% endfor %}
            </datalist>

            <!-- 提示信息与错误反馈 -->
            {% if error %}
            <div class="mt-6 p-4 bg-red-950/60 border border-red-800/80 rounded-xl text-red-300 text-sm">
                {{ error }}
            </div>
            {% endif %}

            {% if matched_start and matched_target %}
            <div class="mt-6 text-sm text-slate-400">
                🎯 <span class="lang-zh">匹配识别：</span><span class="lang-en">Match: </span><strong>{{ matched_start }}</strong> vs <strong>{{ matched_target }}</strong>
                {% if matched_waypoints_str %}
                <br>📍 <span class="lang-zh">途径点：</span><span class="lang-en">Waypoints: </span><span class="text-amber-400">{{ matched_waypoints_str }}</span>
                {% endif %}
            </div>
            {% endif %}

            <!-- 结果区 -->
            {% if paths is not none %}
            <div class="mt-6 p-4 bg-slate-950/80 border border-slate-800 rounded-xl space-y-4">
                <div class="font-bold text-base text-slate-200">
                    <span class="lang-zh">找到 {{ total_count }} 条路径：</span>
                    <span class="lang-en">Found {{ total_count }} paths:</span>
                </div>

                {% if paths %}
                    <div class="text-xs text-amber-400">
                        🔥 <span class="lang-zh">默认展示较短路径（≤{{ default_display_steps }}步）：</span>
                        <span class="lang-en">Shortest paths displayed by default (≤{{ default_display_steps }} steps):</span>
                    </div>
                    {% for p_item in default_paths %}
                    <div class="py-2 border-b border-slate-800/80 text-sm leading-relaxed text-slate-200 last:border-0">
                        <strong>#{{ p_item.index }}</strong> [{{ p_item.steps }} <span class="lang-zh">步</span><span class="lang-en">steps</span>]: 
                        {{ p_item.formatted_html|safe }}
                    </div>
                    {% endfor %}

                    {% if longer_paths %}
                    <details class="mt-4 bg-slate-900 border border-slate-800 rounded-lg p-3">
                        <summary class="cursor-pointer text-red-500 font-bold text-sm hover:text-red-400">
                            📂 <span class="lang-zh">点击展开查看更长的路径 ({{ longer_paths|length }} 条)</span>
                            <span class="lang-en">Click to expand longer paths ({{ longer_paths|length }})</span>
                        </summary>
                        <div class="mt-3 space-y-2">
                            {% for p_item in longer_paths %}
                            <div class="py-2 border-b border-slate-800/80 text-sm leading-relaxed text-slate-200 last:border-0">
                                <strong>#{{ p_item.index }}</strong> [{{ p_item.steps }} <span class="lang-zh">步</span><span class="lang-en">steps</span>]: 
                                {{ p_item.formatted_html|safe }}
                            </div>
                            {% endfor %}
                        </div>
                    </details>
                    {% endif %}

                {% else %}
                    <p class="text-slate-400 text-sm">
                        <span class="lang-zh">未能在当前条件下找到符合要求的路径。</span>
                        <span class="lang-en">No path found under current condition.</span>
                    </p>
                    
                    {% if rev_paths %}
                    <div class="mt-4 pt-3 border-t border-dashed border-slate-800 text-sm">
                        <p class="text-amber-400 font-medium mb-2">
                            💡 <span class="lang-zh">提示：顺向没找到，但找到了 <strong>{{ matched_target }}</strong> 反向叠盒子赢 <strong>{{ matched_start }}</strong> 的路径：</span>
                            <span class="lang-en">Tip: Reverse paths found for <strong>{{ matched_target }}</strong> defeating <strong>{{ matched_start }}</strong>:</span>
                        </p>
                        {% for r_item in rev_paths %}
                        <div class="py-1 text-slate-400">
                            <strong>#{{ r_item.index }}</strong> [{{ r_item.steps }} <span class="lang-zh">步</span><span class="lang-en">steps</span>]: {{ r_item.formatted_html|safe }}
                        </div>
                        {% endfor %}
                    </div>
                    {% endif %}
                {% endif %}
            </div>
            {% endif %}
        </main>
    </div>

    <!-- 双语切换脚本 -->
    <script>
        let currentLang = 'zh';
        function toggleLanguage() {
            currentLang = currentLang === 'zh' ? 'en' : 'zh';
            const zhElements = document.querySelectorAll('.lang-zh');
            const enElements = document.querySelectorAll('.lang-en');
            
            if (currentLang === 'en') {
                zhElements.forEach(el => el.style.display = 'none');
                enElements.forEach(el => el.style.display = 'inline');
                document.getElementById('langBtn').innerText = '🌐 中文 / English';
            } else {
                zhElements.forEach(el => el.style.display = 'inline');
                enElements.forEach(el => el.style.display = 'none');
                document.getElementById('langBtn').innerText = '🌐 English / 中文';
            }
        }

        document.addEventListener('DOMContentLoaded', () => {
            document.querySelectorAll('.lang-en').forEach(el => el.style.display = 'none');
        });

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
