"""三種氣候災難：每局隨機抽一種（玩法一樣，但災情、道具名稱、畫面、劇情、防災知識都不同）

遊戲機制共用六種災情代碼（breach / drain / electric / house_flood / trapped / tree），
每種災難只換「這個代碼在這場災難裡代表什麼」。
內部的三個階段代碼（小雨 / 颱風眼 / 暴雨）也共用，畫面上顯示 phases 裡的名稱。
"""
import random

DISASTERS = {
    # ─────────────────────────── 颱風淹水 ───────────────────────────
    "typhoon": {
        "name": "颱風淹水", "event": "颱風", "meter": "水位", "win_title": "颱風過境，小鎮撐住了！",
        "phases": {"小雨": "小雨", "颱風眼": "颱風眼", "暴雨": "暴雨"},
        "banners": {"颱風眼": "颱風眼來了，雨變小了！", "暴雨": "最後一波暴雨來了！"},
        "incidents": {"breach": "堤防破洞", "drain": "排水溝堵塞", "electric": "電箱冒火花",
                      "house_flood": "民宅淹水", "trapped": "居民受困", "tree": "大樹倒下"},
        "items": {},
        "look": {"band": 0x3a86c8, "foam": 0xcaf0f8, "liquid": 0x4ea8de, "overlay": 0x0b1a2b,
                 "rain": True, "embers": False, "rocks": False},
        "town": "小鎮有河堤、四間民宅、排水溝、電箱、行道樹；倉庫平時就備好沙包、工具和抽水機零件",
        "climate": "氣候變遷讓颱風豪雨比以前更強、更頻繁",
        "knowledge": {
            "breach": "颱風豪雨時不要靠近河堤；家中可事先準備沙包或擋水板。",
            "drain": "颱風來之前先清理住家附近的排水溝，可以大幅減少積水。",
            "electric": "淹水前先關閉總電源，不要碰觸泡水的電器和電箱。",
            "house_flood": "住家淹水時先往高處移動，確認斷電後再抽水與清理。",
            "trapped": "受困時待在高處、保持手機電量並對外聯絡，不要自行涉水。",
            "tree": "颱風天避開行道樹與招牌下方，看到路樹倒塌請通報政府處理。",
        },
        "lines": {
            "breach": ["河堤破了一個洞！水一直灌進來！", "堤防要撐不住了，快拿沙包！"],
            "drain": ["水溝塞滿落葉，路上都積水了啦～", "排水溝堵住了，水退不掉！"],
            "electric": ["電箱在冒火花！好可怕！", "滋滋滋…電箱泡到水了！"],
            "house_flood": ["我家客廳變游泳池了啦！", "水淹進屋子了，救命～"],
            "trapped": ["我被困在家裡出不去！", "水好深，我不敢走出去…"],
            "tree": ["大樹倒下來擋住路了！", "轟！路樹倒了！"],
        },
        "fail": {
            "breach": ("村民", "河堤守不住了……早知道平常就該把堤防補強。"),
            "drain": ("阿嬤", "水溝一直沒清，水都退不掉……下次颱風前一定要先清。"),
            "electric": ("鎮長", "電箱燒壞了，整條街停電……淹水前真的要先斷電。"),
            "house_flood": ("阿嬤", "我家客廳全泡水了……還好人沒事。"),
            "trapped": ("小宇", "有人沒來得及救出來……鄰居之間平常要互相關心。"),
            "tree": ("村民", "路被倒樹擋住，救護車進不來了！"),
        },
        "news": [
            "插播！海水溫度越高，颱風能吸收的能量就越多，所以颱風越來越強。",
            "氣象小知識：空氣越暖，能裝的水氣越多，下起雨來就更猛。",
            "專家提醒，像今晚這種短時間的極端豪雨，在氣候變遷下會越來越常見。",
            "插播！排水系統當初是照以前的雨量設計的，現在的大雨常常超過它的負荷。",
            "氣象局呼籲：颱風來之前就要備好物資、清好水溝，等雨來了就來不及了。",
        ],
        "high": [("氣象主播", "水位快到頂了！極端豪雨超過排水能負荷的量，大家要加快！"),
                 ("村民", "水淹到小腿了……這雨也下得太誇張了吧！")],
        "calm": {"speaker": "鎮長", "line": "雨暫時停了！趁颱風眼把破洞補好、把居民帶到避難所！"},
        "storm": {"speaker": "氣象主播", "line": "最強的雨帶來了！大家互相支援，一定要撐住！"},
        "climate_lines": [
            "以前這種颱風十年才一次，現在幾乎年年來，我們得習慣、更要準備。",
            "海水越來越暖，颱風只會越來越強。今晚能撐住，是因為倉庫裡平時就有東西。",
            "氣象局說這種極端豪雨會越來越常見。所以啊，防災不是颱風來了才做的事。",
        ],
    },

    # ─────────────────────────── 熱浪野火 ───────────────────────────
    "heatwave": {
        "name": "熱浪野火", "event": "熱浪", "meter": "火勢", "win_title": "熱浪退去，小鎮撐住了！",
        "phases": {"小雨": "高溫", "颱風眼": "傍晚降溫", "暴雨": "熱浪高峰"},
        "banners": {"颱風眼": "傍晚起風，溫度降了一點！", "暴雨": "熱浪高峰來了，火勢變猛！"},
        "incidents": {"breach": "山火逼近", "drain": "乾草堆積", "electric": "電線過載",
                      "house_flood": "民宅起火", "trapped": "居民中暑", "tree": "枯樹倒塌"},
        "items": {},
        "look": {"band": 0xe76f51, "foam": 0xffd166, "liquid": 0xf4a261, "overlay": 0xff7b00,
                 "rain": False, "embers": True, "rocks": False},
        "town": "小鎮在山腳下，後山是乾燥的樹林；有四間民宅、電箱、路樹；倉庫平時就備好水桶、鐮刀、滅火器、飲用水和冰毛巾",
        "climate": "氣候變遷讓熱浪更熱、更長，乾燥的草木更容易起火",
        "knowledge": {
            "breach": "野火靠近時，事先在住家附近準備好水源；接到撤離通知就要馬上離開，滅火交給消防員。",
            "drain": "割除住家周圍的乾草、清出一圈防火帶，火就不容易延燒到房子。",
            "electric": "熱浪時冷氣用電暴增，大電器不要插在同一條延長線；電線發燙就先關電源、拔插頭。",
            "house_flood": "滅火器口訣「拉、瞄、壓、掃」：拉插銷、瞄準火源底部、壓握把、左右掃；火太大就立刻逃生打 119。",
            "trapped": "中暑急救：移到陰涼處、用冰毛巾或冷水降溫，意識清楚才慢慢給水，並撥打 119。",
            "tree": "倒下的枯木和枯枝要清走，堆在路邊遇到高溫和火星很容易起火。",
        },
        "lines": {
            "breach": ["後山的火燒過來了！快提水！", "火線一直往鎮上靠近！"],
            "drain": ["路邊的乾草一點火就著…", "乾草長到膝蓋了，好危險！"],
            "electric": ["冷氣開太多，延長線在發燙！", "插座冒煙了，聞到燒焦味！"],
            "house_flood": ["我家廚房起火了！", "救命～屋子燒起來了！"],
            "trapped": ["我頭好暈…好熱…", "阿公中暑倒在家門口了！"],
            "tree": ["枯樹被熱風吹倒了！", "乾掉的大樹倒下來擋路了！"],
        },
        "fail": {
            "breach": ("村民", "火線燒到鎮上了……水源要事先準備好才來得及。"),
            "drain": ("阿嬤", "乾草一點就著……熱浪來之前真的要先割乾淨。"),
            "electric": ("鎮長", "電線燒壞了，整條街停電……用電不能一次插那麼多。"),
            "house_flood": ("阿嬤", "廚房燒掉了……還好大家都先跑出來了。"),
            "trapped": ("小宇", "有鄰居中暑送醫了……熱浪天要多關心獨居的長輩。"),
            "tree": ("村民", "枯樹倒在路上，消防車開不進來！"),
        },
        "news": [
            "插播！地球越來越暖，熱浪出現得更頻繁、也持續得更久。",
            "氣象小知識：天氣又熱又乾，草木裡的水分被蒸發，就變得很容易起火。",
            "專家提醒，城市裡的柏油和水泥會吸熱，晚上也降不了溫，叫做熱島效應。",
            "插播！熱浪來的時候大家都開冷氣，用電量暴增，電線更容易過熱。",
            "氣象局呼籲：高溫特報時多喝水、避開中午外出，也要關心家裡的長輩。",
        ],
        "high": [("氣象主播", "火勢快燒到鎮中心了！高溫加上乾燥，火燒得特別快，大家要加快！"),
                 ("村民", "熱到喘不過氣……煙也越來越濃了！")],
        "calm": {"speaker": "鎮長", "line": "傍晚起風降溫了！趁現在割乾草、裝滿水桶、照顧中暑的人！"},
        "storm": {"speaker": "氣象主播", "line": "熱浪高峰來了！氣溫還在往上衝，大家互相支援！"},
        "climate_lines": [
            "以前夏天熱幾天就過了，現在熱浪一來就是好幾個禮拜，我們得習慣、更要準備。",
            "天氣越熱越乾，火就越容易燒起來。今晚能撐住，是因為平時就把枯草清了、工具備了。",
            "專家說熱浪會越來越常見。所以啊，防災不只是颱風天的事。",
        ],
    },

    # ─────────────────────────── 豪雨土石流 ───────────────────────────
    "landslide": {
        "name": "豪雨土石流", "event": "豪雨", "meter": "土石", "win_title": "豪雨停了，小鎮撐住了！",
        "phases": {"小雨": "連日豪雨", "颱風眼": "雨勢暫歇", "暴雨": "山區暴雨"},
        "banners": {"颱風眼": "雨勢暫時停了，快加固！", "暴雨": "山區暴雨來了，土石又在滑落！"},
        "incidents": {"breach": "土石滑落", "drain": "溝渠塞泥沙", "electric": "電箱泡泥",
                      "house_flood": "住戶撤離", "trapped": "居民受困", "tree": "落石擋路"},
        "items": {"trash": "泥沙"},
        "look": {"band": 0x8d6e4b, "foam": 0xd4a373, "liquid": 0x9c6644, "overlay": 0x1b1a12,
                 "rain": True, "embers": False, "rocks": True},
        "town": "小鎮在山坡下，後山的土石因為連日下雨變得鬆軟；有四間民宅、排水溝、電箱；倉庫平時就備好鏟子、十字鎬、鐵鎚、警示帶、木樁和鐵絲網",
        "climate": "氣候變遷讓極端豪雨變多，山坡吸飽水就容易崩塌",
        "knowledge": {
            "breach": "山坡邊可以用擋土設施減緩土石滑落；但看到山坡裂縫、滲水或落石，最重要的是立刻撤離。",
            "drain": "定期清理排水溝和山坡截水溝，讓雨水有地方排走，土石就不容易滑落。",
            "electric": "看到被泥水泡到的電箱或掉落的電線不要靠近，拉起警示範圍、提醒路人，並通報台電 1911。",
            "house_flood": "豪雨特報發布時，土石流潛勢區的住戶要提早撤離到避難所，不要等土石下來才跑。",
            "trapped": "受困時保持冷靜，敲打或用手電筒讓救援人員找到你；救援要多人合作，不要單獨冒險。",
            "tree": "看到道路有落石不要停車觀看，繞道並通報，也要小心後續還會再落。",
        },
        "lines": {
            "breach": ["後山的泥土滑下來了！", "土石一直往下沖，快擋住！"],
            "drain": ["溝裡全是泥巴，水排不出去！", "截水溝塞滿泥沙了啦～"],
            "electric": ["電箱被泥巴埋了一半，滋滋響！", "電線垂下來了，好危險！"],
            "house_flood": ["後山在轟隆隆響…我們要走嗎？", "阿嬤還在家裡看電視，沒聽到廣播！"],
            "trapped": ["土石把門堵住了，我出不去！", "救命！我被困在土堆後面…"],
            "tree": ["大石頭滾下來擋住路了！", "轟！落石！路不通了！"],
        },
        "fail": {
            "breach": ("村民", "土石沖進鎮裡了……山坡平常就該做好水土保持。"),
            "drain": ("阿嬤", "水溝塞住，雨水全往山坡灌……下雨前一定要先清。"),
            "electric": ("鎮長", "電箱短路，整條街停電……看到受損的電箱要趕快通報。"),
            "house_flood": ("阿嬤", "土石沖進屋裡了……豪雨特報一出來就該先走。"),
            "trapped": ("小宇", "有人還困在土堆後面……救援要大家一起來。"),
            "tree": ("村民", "落石把路堵死了，救援車進不來！"),
        },
        "news": [
            "插播！空氣越暖能裝的水氣越多，所以短時間的超大豪雨越來越常見。",
            "氣象小知識：連續下好幾天雨，山坡的土吸飽了水，就會變重、變鬆，容易滑落。",
            "專家提醒，山坡上的樹根可以抓住泥土，亂砍樹會讓土石流更容易發生。",
            "插播！土石流發生前常有徵兆：溪水突然變混濁、聽到山裡有轟隆聲。",
            "氣象局呼籲：山區豪雨特報時，住在山坡邊的居民要提早撤離。",
        ],
        "high": [("氣象主播", "土石快沖到鎮中心了！山坡吸飽了雨水，大家要加快！"),
                 ("村民", "泥巴已經淹到腳踝了……這雨到底要下到什麼時候！")],
        "calm": {"speaker": "鎮長", "line": "雨暫時停了！趁現在清溝渠、通知山坡邊的住戶撤離！"},
        "storm": {"speaker": "氣象主播", "line": "山區暴雨又來了！土石還會再滑，大家互相支援！"},
        "climate_lines": [
            "以前一年才一兩次這種豪雨，現在越來越常見，山坡也越來越撐不住。",
            "雨下得越兇，山坡就越危險。今晚能撐住，是因為平時就清了溝、備了物資。",
            "專家說極端豪雨會越來越多。所以啊，平常的水土保持和撤離演練都不能少。",
        ],
    },
}

# ── 劇情章節：每個階段一章，角色交代一個「跟主題有關的任務」，做到／沒做到劇情會不一樣 ──
# theme：這章想傳達的事（準備／互助／氣候）；goal：要解決哪些災情、幾件；
# penalty：沒做到時的後果（計量條上升多少）；bonus：做到的獎勵金幣
CHAPTERS = {
    "typhoon": {
        "小雨": {"title": "第一章　颱風前的準備", "theme": "平時準備", "goal": ["drain"], "need": 2, "bonus": 30, "penalty": 8,
                "goal_text": "清通排水溝",
                "intro": ("鎮長", "颱風還沒到最強，趁現在先把排水溝清乾淨，等一下大雨水才有路走！"),
                "success": ("阿嬤", "水溝通了！以前都等淹水才清，這次先準備好，等一下就不怕了。"),
                "fail": ("村民", "水溝沒清完……暴雨一來，水一定退不掉，鎮上會淹得更快。")},
        "颱風眼": {"title": "第二章　趁雨停救人", "theme": "鄰里互助", "goal": ["trapped", "house_flood"], "need": 2, "bonus": 40, "penalty": 8,
                 "goal_text": "救出受困居民、幫民宅抽水",
                 "intro": ("小宇", "雨停了！阿嬤說低窪那邊還有鄰居沒出來，大家分頭去幫忙！"),
                 "success": ("鎮長", "一個救人、一個抽水，分工就是快！鄰居之間互相照顧，比什麼都重要。"),
                 "fail": ("小宇", "有鄰居還困在家裡……下次要更早去敲門關心。")},
        "暴雨": {"title": "第三章　守住堤防", "theme": "氣候變遷", "goal": ["breach"], "need": 2, "bonus": 50, "penalty": 10,
               "goal_text": "補好堤防破洞",
               "intro": ("氣象主播", "最強雨帶到了！這種雨量以前很少見，現在幾乎年年都有，堤防一定要守住！"),
               "success": ("鎮長", "堤防守住了！天氣越來越極端，但只要準備夠、大家一起扛，小鎮就撐得住。"),
               "fail": ("村民", "堤防破了，河水灌進來……以前的堤防，擋不住現在的雨了。")},
    },
    "heatwave": {
        "小雨": {"title": "第一章　清出防火帶", "theme": "平時準備", "goal": ["drain"], "need": 2, "bonus": 30, "penalty": 8,
                "goal_text": "割掉乾草、清出防火帶",
                "intro": ("鎮長", "火還沒燒過來，先把房子旁邊的乾草割掉，清出一圈防火帶！"),
                "success": ("阿嬤", "草割乾淨了，火就沒東西可以燒過來。這種事真的要平常就做。"),
                "fail": ("村民", "乾草還在……火星一飄過來，整片都會燒起來。")},
        "颱風眼": {"title": "第二章　照顧獨居長輩", "theme": "鄰里互助", "goal": ["trapped", "electric"], "need": 2, "bonus": 40, "penalty": 8,
                 "goal_text": "照顧中暑的人、處理過載的電線",
                 "intro": ("阿嬤", "隔壁阿公一個人住，這麼熱冷氣又開到電線發燙，快去看看他！"),
                 "success": ("小宇", "阿公喝了水、敷了冰毛巾，說好多了！熱浪天就是要互相關心。"),
                 "fail": ("阿嬤", "阿公中暑送醫了……熱浪天真的要多去敲門看看長輩。")},
        "暴雨": {"title": "第三章　一起滅火", "theme": "氣候變遷", "goal": ["house_flood", "breach"], "need": 2, "bonus": 50, "penalty": 10,
               "goal_text": "撲滅民宅火災、擋住山火",
               "intro": ("氣象主播", "熱浪高峰！地球越來越暖，這種高溫以後會更常見，大家一起提水滅火！"),
               "success": ("鎮長", "火滅了！天氣越來越熱，但只要水源備好、大家一起提水，就不怕。"),
               "fail": ("村民", "火燒進鎮上了……這麼熱的天氣，以前真的沒遇過。")},
    },
    "landslide": {
        "小雨": {"title": "第一章　讓雨水有路走", "theme": "平時準備", "goal": ["drain"], "need": 2, "bonus": 30, "penalty": 8,
                "goal_text": "清通塞住的溝渠",
                "intro": ("鎮長", "後山開始冒混濁的水了！先把溝渠清通，讓雨水有路走，山坡才不會吸飽水！"),
                "success": ("村民", "溝渠通了，水都往下排走了。平常就把水溝顧好，真的有差。"),
                "fail": ("阿嬤", "溝渠還是塞著……雨水全往山坡裡灌，等一下更危險。")},
        "颱風眼": {"title": "第二章　提早撤離", "theme": "鄰里互助", "goal": ["house_flood"], "need": 2, "bonus": 40, "penalty": 8,
                 "goal_text": "通知山坡邊的住戶撤離",
                 "intro": ("鎮長", "趁雨停，挨家挨戶去通知山坡邊的住戶，現在就撤離，不要等土石下來！"),
                 "success": ("阿嬤", "大家都到避難所了。還好你們來敲門，我根本沒聽到廣播。"),
                 "fail": ("小宇", "還有人沒撤離……豪雨特報一發布，就應該先走的。")},
        "暴雨": {"title": "第三章　合力救援", "theme": "氣候變遷", "goal": ["trapped", "breach"], "need": 2, "bonus": 50, "penalty": 10,
               "goal_text": "合力挖出受困居民、架擋土柵",
               "intro": ("氣象主播", "山區暴雨！這種短時間的超大豪雨越來越常見，吸飽水的山坡隨時會滑！"),
               "success": ("鎮長", "人救出來了！雨越下越兇，但大家一起挖、一起擋，就救得了人。"),
               "fail": ("村民", "土石又滑下來了……以前的山坡，撐不住現在的雨。")},
    },
}

# ── 局間防災建設：用金幣買，每人開局帶一樣（平時投資減災，災時就輕鬆）──────────
# effect 由 game.py 套用；icon 用道具圖示
FACILITIES = {
    "green": {"name": "社區綠地", "price": 100, "icon": "Hoe",
              "desc": "清理類災情（排水溝、乾草、溝渠）處理時間縮短三分之一",
              "why": "透水鋪面和綠地讓雨水滲進土裡，樹蔭也讓熱浪降溫"},
    "alarm": {"name": "預警廣播站", "price": 150, "icon": "ScrollThunder",
              "desc": "每件災情的倒數時間多 20%",
              "why": "越早收到警報，就有越多時間準備和撤離"},
    "pond": {"name": "滯洪蓄水池", "price": 180, "icon": "WaterBucket",
             "desc": "計量條（水位、火勢、土石）上升速度變慢 15%",
             "why": "大雨時先把水存起來，乾旱和火災時也有水可用"},
    "levee": {"name": "強化防線", "price": 200, "icon": "CrateEmpty",
              "desc": "堤防破洞、山火逼近、土石滑落都少交一次",
              "why": "平時補強堤防、防火帶和擋土牆，災害來時就擋得住"},
    "aid": {"name": "社區急救站", "price": 250, "icon": "Heart",
            "desc": "開局多一顆愛心",
            "why": "就近有急救資源，受傷或中暑的人能馬上被照顧"},
}
START_FUND = 100            # 新玩家的第一筆防災基金（剛好可以買社區綠地）

# 道具：名稱與圖示（圖示在 static/assets/items）
ITEM_INFO = {
    # 颱風
    "bag": ("空袋", "Bag"), "sandbag": ("沙包", "MoneyBag"), "rake": ("耙子", "Hoe"), "gloves": ("絕緣手套", "Interact"),
    "ring": ("救生圈", "Calamari"), "axe": ("斧頭", "Axe"), "motor": ("馬達", "BarIron"), "hose": ("水管", "Scroll"),
    "pump": ("抽水機", "WateringCan"), "trash": ("淤泥垃圾", "Rock"),
    # 熱浪
    "bucket": ("空桶", "EmptyPot"), "water": ("滿水桶", "WaterBucket"), "sickle": ("鐮刀", "Sickle"),
    "extinguisher": ("滅火器", "Extinguisher"), "drink": ("飲用水", "WaterPot"), "towel": ("冰毛巾", "ScrollIce"),
    "branch": ("枯枝", "Branch"),
    # 土石流
    "shovel": ("鏟子", "Shovel"), "pickaxe": ("十字鎬", "Pickaxe"), "hammer": ("鐵鎚", "Hammer"),
    "tape": ("警示帶", "ScrollThunder"), "stake": ("木樁", "Branch"), "wire": ("鐵絲網", "BarSilver"),
    "fence": ("擋土柵", "CrateEmpty"), "rubble": ("碎石", "Rock"),
}

# how：tap＝交出道具（count 次）／hold＝按住（need 是 None 就是空手）／pump＝交出後自己跑進度
#      escort＝交出道具（need 是 None 就是空手按一下）後居民跟著走到避難所／multi＝要交齊好幾樣，交齊後居民跟著走
# team：要幾個人「同時」按住才會有進度；yield：處理完掉出要送去清運的東西；stun：沒帶 need 靠近會被電
KITS = {
    "typhoon": {
        "crates": ["rake", "gloves", "ring", "axe", "bag", "motor", "hose"],
        "process": {"in": "bag", "out": "sandbag", "secs": 1.2, "label": "沙堆"},
        "bench": {"parts": ["motor", "hose"], "product": "pump", "secs": 2.0, "label": "工作台"},
        "truck": {"accepts": ["trash"], "label": "垃圾車"},
        "recipes": {
            "breach": {"how": "tap", "need": "sandbag", "count": 3, "badge": "放下",
                       "steps": ["i:bag", "→", "p:沙堆", "→", "i:sandbag", "×3"]},
            "drain": {"how": "hold", "need": "rake", "work": 2.0, "yield": "trash", "badge": "按住",
                      "steps": ["i:rake", "→", "p:現場按住", "→", "i:trash", "→", "p:垃圾車"], "card": ["i:rake", "→", "p:現場"]},
            "electric": {"how": "hold", "need": "gloves", "work": 1.6, "stun": True, "badge": "按住",
                         "steps": ["i:gloves", "→", "p:現場"]},
            "house_flood": {"how": "pump", "need": "pump", "badge": "放下",
                            "steps": ["i:motor", "+", "i:hose", "→", "p:工作台", "→", "i:pump"],
                            "card": ["i:motor", "+", "i:hose", "→", "p:工作台"]},
            "trapped": {"how": "escort", "need": "ring", "badge": "帶走", "steps": ["i:ring", "→", "p:避難所"]},
            "tree": {"how": "hold", "need": "axe", "work": 2.0, "badge": "按住", "steps": ["i:axe", "→", "p:現場"]},
        },
    },
    "heatwave": {
        # 招牌玩法：到水井打水、接力提水滅火；中暑要「飲用水＋冰毛巾」都送到；滅火器要兩個人一起噴
        "crates": ["sickle", "extinguisher", "drink", "axe", "bucket", "towel", "bucket"],
        "process": {"in": "bucket", "out": "water", "secs": 1.0, "label": "水井", "look": "well"},
        "bench": None,
        "truck": {"accepts": ["branch"], "label": "清運車"},
        "recipes": {
            "breach": {"how": "tap", "need": "water", "count": 3, "badge": "潑水",
                       "steps": ["i:bucket", "→", "p:水井", "→", "i:water", "×3"],
                       "card": ["i:bucket", "→", "p:水井", "→", "i:water"]},
            "drain": {"how": "hold", "need": "sickle", "work": 2.2, "badge": "按住",
                      "steps": ["i:sickle", "→", "p:割出防火帶"], "card": ["i:sickle", "→", "p:現場"]},
            "electric": {"how": "hold", "need": None, "work": 1.4, "badge": "空手",
                         "steps": ["p:空手", "→", "p:按住拔插頭"]},
            "house_flood": {"how": "hold", "need": "extinguisher", "work": 2.4, "team": 2, "time": 52, "badge": "兩人",
                            "steps": ["i:extinguisher", "+", "i:extinguisher", "→", "p:兩人一起按住"],
                            "card": ["i:extinguisher", "×2", "→", "p:一起按住"]},
            "trapped": {"how": "multi", "need": ["drink", "towel"], "badge": "照顧",
                        "steps": ["i:drink", "+", "i:towel", "→", "p:帶去避難所"]},
            "tree": {"how": "hold", "need": "axe", "work": 2.0, "yield": "branch", "badge": "按住",
                     "steps": ["i:axe", "→", "p:現場按住", "→", "i:branch", "→", "p:清運車"], "card": ["i:axe", "→", "p:現場"]},
        },
    },
    "landslide": {
        # 招牌玩法：工作台做擋土柵；空手挨家挨戶通知撤離；受困居民要兩個人一起挖
        "crates": ["shovel", "tape", "pickaxe", "hammer", "stake", "wire", "stake"],
        "process": None,
        "bench": {"parts": ["stake", "wire"], "product": "fence", "secs": 2.0, "label": "工作台"},
        "truck": {"accepts": ["trash", "rubble"], "label": "清運車"},
        "recipes": {
            "breach": {"how": "tap", "need": "fence", "count": 2, "badge": "架設", "time": 55,
                       "steps": ["i:stake", "+", "i:wire", "→", "p:工作台", "→", "i:fence", "×2"],
                       "card": ["i:stake", "+", "i:wire", "→", "p:工作台"]},
            "drain": {"how": "hold", "need": "shovel", "work": 2.0, "yield": "trash", "badge": "按住",
                      "steps": ["i:shovel", "→", "p:現場按住", "→", "i:trash", "→", "p:清運車"], "card": ["i:shovel", "→", "p:現場"]},
            "electric": {"how": "tap", "need": "tape", "count": 1, "stun": True, "badge": "圍起來",
                         "steps": ["i:tape", "→", "p:現場（別空手靠近）"], "card": ["i:tape", "→", "p:現場"]},
            "house_flood": {"how": "escort", "need": None, "badge": "通知",
                            "steps": ["p:空手按一下", "→", "p:帶去避難所"]},
            "trapped": {"how": "hold", "need": "pickaxe", "work": 2.6, "team": 2, "time": 55, "badge": "兩人",
                        "steps": ["i:pickaxe", "+", "i:pickaxe", "→", "p:兩人一起按住"],
                        "card": ["i:pickaxe", "×2", "→", "p:一起按住"]},
            "tree": {"how": "hold", "need": "hammer", "work": 2.0, "yield": "rubble", "badge": "按住",
                     "steps": ["i:hammer", "→", "p:現場按住", "→", "i:rubble", "→", "p:清運車"], "card": ["i:hammer", "→", "p:現場"]},
        },
    },
}

KEYS = list(DISASTERS)


def get(key):
    return DISASTERS.get(key) or DISASTERS["typhoon"]


def kit(key):
    return KITS.get(key) or KITS["typhoon"]


def pick(exclude=None):
    """隨機抽一種災難（盡量不要和上一局一樣）"""
    options = [k for k in KEYS if k != exclude] or KEYS
    return random.choice(options)
