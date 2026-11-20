"""视觉词表与图像提示词规则（服务端词典）。

与 analyzer 同一套纪律：纯数据 + 纯函数、零 IO、零第三方依赖、结果可复现。

词条用「竖线分隔的紧凑行」而不是字典字面量：一行一个词条，便于 diff 与扩词，
解析后统一成 `(中文, 英文, 别名元组, 场景元组)`。
字段顺序固定为 `中文|english|别名1,别名2|MK EC`；负面词多一个 `等级` 字段。

场景编码：MK 营销 / EC 电商 / IL 插画 / AV 头像 / PS 海报 / CD 概念。
本模块是 [`docs/image-prompt/VISUAL-TERMS-v1.0.md`] 的可执行子集（v1 取 140 条高频项），
文档保持全量 325 条，扩词时两侧同步。
"""

from __future__ import annotations

import re

# ---------------------------------------------------------------- 8 段结构
# 顺序不可调换：主体最先（权重最高），负面最后（不污染主体语义）。
SEGMENT_ORDER = ("subject", "setting", "composition", "lighting",
                 "style", "texture", "technical", "negative")
SEGMENT_LABEL = {
    "subject": ("主体与动作", "subject"),
    "setting": ("场景与环境", "setting"),
    "composition": ("构图与视角", "composition"),
    "lighting": ("光线与氛围", "lighting"),
    "style": ("风格与媒介", "style"),
    "texture": ("材质与细节", "texture"),
    "technical": ("技术参数", "technical"),
    "negative": ("负面约束", "negative"),
}
# S6 为选填段：EC/CD 默认补，其余场景缺省不补，避免为凑长度堆材质词。
TEXTURE_REQUIRED = ("EC", "CD")

# ---------------------------------------------------------------- 场景
SCENES = {
    "MK": ("营销配图", "marketing visual"),
    "EC": ("电商主图", "e-commerce hero"),
    "IL": ("插画封面", "illustration"),
    "AV": ("头像人设", "avatar"),
    "PS": ("海报展板", "poster"),
    "CD": ("概念分镜", "concept art"),
}
DEFAULT_SCENE = "MK"

_SCENE_WORDS = (
    ("商品详情页", "EC"), ("详情页", "EC"), ("白底图", "EC"), ("主图", "EC"),
    ("商品图", "EC"), ("产品图", "EC"), ("电商", "EC"),
    ("人设图", "AV"), ("虚拟形象", "AV"), ("头像", "AV"), ("立绘", "AV"),
    ("概念设计", "CD"), ("概念图", "CD"), ("分镜图", "CD"), ("分镜稿", "CD"),
    ("主视觉", "PS"), ("易拉宝", "PS"), ("展板", "PS"), ("海报", "PS"),
    ("插画", "IL"), ("绘本", "IL"), ("封面", "IL"), ("漫画", "IL"),
    ("宣传图", "MK"), ("营销图", "MK"), ("推广图", "MK"), ("配图", "MK"),
)
# 长词优先：避免「详情页」被更短的「页」类词抢先（当前无短词，保留以防扩词踩坑）
SCENE_KEYWORDS = tuple(sorted(_SCENE_WORDS, key=lambda kv: -len(kv[0])))

# 各场景的默认基调：用户没说的段按此补齐，并在 defaults 里标注来源。
SCENE_DEFAULT = {
    "MK": {"composition": "三分法", "lighting": "自然光", "style": "写实摄影",
           "setting": "户外自然场景，背景层次清晰，不抢主体，中景范围内无干扰元素"},
    "EC": {"composition": "中心构图", "lighting": "影棚布光", "style": "商业产品摄影",
           "texture": "哑光", "setting": "纯白无缝背景，无杂物，主体完整入画"},
    "IL": {"composition": "三分法", "lighting": "柔光", "style": "扁平插画",
           "texture": "细腻纹理",
           "setting": "简洁背景，主体突出，画面留白得当"},
    "AV": {"composition": "中心构图", "lighting": "蝴蝶光", "style": "扁平插画",
           "setting": "浅灰纯色背景，背景干净无渐变噪声"},
    "PS": {"composition": "对称构图", "lighting": "硬光", "style": "极简主义",
           "texture": "细腻纹理",
           "setting": "渐变背景，四周留边，背景无杂物"},
    "CD": {"composition": "引导线", "lighting": "低调", "style": "电影感",
           "texture": "细腻纹理",
           "setting": "环境细节丰富的实景空间，前中后景分出层次"},
}
# 景别按场景给默认值，避免每张图都写成「中景」。
SCENE_SHOT = {"MK": "平视中景", "EC": "平视特写", "IL": "平视中景",
              "AV": "平视近景", "PS": "平视全景", "CD": "平视远景"}

# ---------------------------------------------------------------- 比例
RATIO_RE = re.compile(r"(\d{1,2})\s*[:：比]\s*(\d{1,2})")
RATIO_WORDS = (("超宽幅", "21:9"), ("宽幅", "21:9"), ("横版", "16:9"), ("横屏", "16:9"),
               ("竖屏", "9:16"), ("竖版", "9:16"), ("方图", "1:1"), ("正方形", "1:1"),
               ("方形", "1:1"), ("长图", "2:3"))
RATIO_DEFAULT = {"MK": "16:9", "EC": "1:1", "IL": "2:3", "AV": "1:1",
                 "PS": "2:3", "CD": "21:9"}
RATIOS = ("1:1", "4:5", "3:4", "16:9", "9:16", "2:3", "21:9")

# ---------------------------------------------------------------- 平台方言
PLATFORMS = ("generic", "mj", "sdxl", "flux", "dalle3")
PLATFORM_ALIAS = {
    "": "generic", "generic": "generic", "通用": "generic",
    "mj": "mj", "midjourney": "mj", "v6": "mj",
    "sdxl": "sdxl", "sd": "sdxl", "stable diffusion": "sdxl",
    "flux": "flux",
    "dalle3": "dalle3", "dall-e": "dalle3", "dalle": "dalle3", "dall·e": "dalle3",
}
PLATFORM_LABEL = {
    "generic": ("通用", "generic"),
    "mj": ("Midjourney v6", "Midjourney v6"),
    "sdxl": ("SDXL", "SDXL"),
    "flux": ("Flux", "Flux"),
    "dalle3": ("DALL·E 3", "DALL·E 3"),
}

# ---------------------------------------------------------------- 词表（140 条）
_TERM_DATA = {
    "composition": """
三分法|rule of thirds|九宫格,三分构图|MK IL CD PS
中心构图|centered composition|居中构图,中央构图|EC AV PS
对称构图|symmetrical composition|镜像构图|PS CD
对角线构图|diagonal composition|斜线构图|MK CD
引导线|leading lines|汇聚线|CD PS
框架构图|framing|画中画,门窗取景|CD IL
前景层次|foreground layering|前景遮挡|MK CD
负空间|negative space|留白区,空白区|PS AV
黄金分割|golden ratio|黄金比例|PS AV
仰视|low angle|低角度,仰拍|MK CD
俯视|high angle|高角度,俯拍|MK CD
平视|eye level|视平线,平拍|MK EC IL AV PS CD
鸟瞰|bird's-eye view|顶拍,正上方|PS CD
浅景深|shallow depth of field|背景虚化,景深浅|AV EC MK
深景深|deep focus|全景清晰|CD PS
极简构图|minimalist composition|少元素构图,克制构图|PS AV EC
满版构图|full-bleed composition|满幅构图,无边框|PS CD
中心留空|centered empty space|中央留白,中心留位|PS
版式留白|layout whitespace|排版留白|PS MK
上方留白|top whitespace|顶部留白,上方留位|PS IL
右侧留白|right-side whitespace|右侧留位,右留白|MK PS
左侧留白|left-side whitespace|左侧留位,左留白|MK PS
平铺构图|flat lay|俯拍平铺,摆拍|EC MK
S 形构图|S-curve composition|曲线引导|CD IL
""",
    "lighting": """
自然光|natural light|环境光,天光|MK CD IL
黄金时刻|golden hour|日落光,日出光|MK CD
蓝调时刻|blue hour|暮蓝,日落后冷光|CD PS
正午硬光|harsh midday light|顶头光,正午光|MK CD
顺光|front lighting|正面光|EC AV
侧光|side lighting|侧向光|EC CD
逆光|backlighting|背光|IL CD
侧逆光|side-back lighting|发丝光|MK AV
顶光|top lighting|上方光|CD
底光|under lighting|下方光|CD
伦勃朗光|Rembrandt lighting|三角光|AV
蝴蝶光|butterfly lighting|美人光|AV EC
柔光|soft light|柔和光,软光|EC AV MK
硬光|hard light|强光,硬边光|MK CD
窗光|window light|侧窗光,自然窗光|MK IL
霓虹光|neon lighting|霓虹灯,彩色管光|CD
烛光|candlelight|烛火,烛火光|IL CD
体积光|volumetric light|丁达尔光,光束|CD PS
轮廓光|rim light|边缘光,分离光|EC AV
高调|high-key|高亮调,亮调|EC AV
低调|low-key|暗调,低调光|CD IL
明暗对比|chiaroscuro|强明暗,光影对比|CD PS
雾气|atmospheric fog|薄雾,晨雾|CD IL
影棚布光|studio lighting|影棚光,棚内布光|EC AV
""",
    "style": """
写实摄影|photorealistic photography|真实照片,超写实|MK EC IL AV PS CD
纪实摄影|documentary photography|纪实风,抓拍风|MK CD
商业产品摄影|commercial product photography|产品摄影,商业棚拍|EC MK
时尚大片|fashion editorial|时尚杂志,editorial|MK AV
电影感|cinematic|电影感调色,宽银幕感|CD PS MK
概念设定|concept art|概念图,概念设计,设定图|CD MK PS
胶片摄影|film photography|胶片风,菲林|IL CD
黑白摄影|black-and-white photography|黑白照片,单色照片|PS CD
水彩|watercolor|水彩晕染|IL PS
油画|oil painting|厚涂油画|IL PS
素描|pencil sketch|铅笔稿,素描稿|IL
水墨|ink wash painting|国画水墨,写意|IL PS
扁平插画|flat illustration|扁平风,矢量平涂|AV IL PS
矢量插画|vector illustration|矢量图|AV PS
等距插画|isometric illustration|等轴插画|IL PS
3D 渲染|3D render|三维渲染,C4D 风|EC AV CD
黏土动画|claymation|黏土风,橡皮泥|AV IL
像素艺术|pixel art|像素风,8bit|IL AV
赛博朋克|cyberpunk|赛博,霓虹未来|CD
蒸汽朋克|steampunk|蒸汽机械,黄铜齿轮|CD IL
极简主义|minimalism|极简风,性冷淡风|PS EC AV
国潮插画|Chinese-chic illustration|新国潮,国风插画|MK PS IL
日式动画赛璐璐|anime cel shading|赛璐璐,日式动画|AV IL
低多边形|low poly|低模,几何切面|AV CD
波普艺术|pop art|波普|PS IL
复古海报|retro poster|老海报,复古印刷|PS MK
拼贴|collage|拼贴画,剪贴|PS IL
微缩模型|miniature diorama|微缩场景,模型感|CD IL
建筑效果图|architectural rendering|建筑渲染,效果图|PS CD
""",
    "texture": """
金属拉丝|brushed metal|拉丝金属|EC CD
磨砂玻璃|frosted glass|毛玻璃|EC PS
陶瓷|ceramic|瓷质|EC MK
大理石|marble|石材纹理|PS EC
混凝土|concrete|水泥|CD PS
原木|natural wood|实木,木纹|MK CD
皮革|leather|真皮,皮纹|EC AV
织物|fabric|布料,织纹|EC MK
丝绸|silk|缎面,真丝|EC AV
毛绒|plush|绒毛,长毛绒|AV IL
水珠|water droplets|水滴,凝结水|EC MK
烟雾|smoke|烟气|CD PS
做旧|weathered|旧化,磨损|CD IL
半透明|translucent|透光,半透|EC PS
反光|reflective|镜面反光|EC CD
哑光|matte finish|雾面,不反光|EC AV
黄铜|brass|铜金色|CD IL
碳纤维|carbon fiber|碳纤纹理|EC CD
冰晶|ice crystal|冰面,霜|EC CD
金属箔|metallic foil|烫金,金箔|PS EC
""",
    "quality": """
高分辨率|high resolution|高清|MK EC IL AV PS CD
超精细细节|ultra-detailed|细节拉满|EC CD
锐利对焦|sharp focus|焦点锐利|EC AV
电影级调色|cinematic color grading|电影调色|CD MK
干净背景|clean background|背景干净|EC AV
无缝背景|seamless backdrop|无缝纸,无接缝背景|EC
白底|white background|纯白底,白背景|EC
真实反射|realistic reflections|物理反射|EC CD
胶片颗粒|film grain|颗粒感|IL CD
低噪点|low noise|无噪点,降噪|CD EC
背景虚化|bokeh|光斑,焦外|AV EC
微距细节|macro detail|近摄细节|EC
低饱和|low saturation|低彩度,灰调|PS AV
青橙色调|teal and orange|青橙调色|CD MK
莫兰迪色|Morandi palette|高级灰,低饱和配色|PS AV
高光细节|highlight detail|高光不溢出|EC CD
""",
}

# 负面词：等级 base=通用必含、person=含人物时、cond=写实/画质条件项、scene=场景追加
_NEG_DATA = """
低质量|low quality|糊图,劣质|base
模糊|blurry|发虚,不清楚|base
比例畸变|bad proportions|变形,走形|base
文字水印|text watermark|水印字,角标|base
噪点|noisy|颗粒噪点|cond
过曝|overexposed|死白,爆光|cond
欠曝|underexposed|死黑|cond
多余肢体|extra limbs|多余手臂,多腿|person
多余手指|extra fingers|六指|person
缺失手指|missing fingers|断指|person
面部崩坏|deformed face|脸崩,五官错位|person
扭曲手部|bad hands|手部崩坏|person
过度磨皮|over-smoothed skin|磨皮过度|person
签名|signature|作者签名|scene
乱码文字|gibberish text|假字,错字招牌|scene
logo|logo|品牌标识|scene
主体裁切|cropped subject|主体出框|scene
边缘裁切|edge cutoff|裁边,切边|scene
杂乱背景|cluttered background|背景杂乱,元素太多|cond
重复元素|duplicated elements|复制人,重影|cond
主体压字|text over subject|文字压主体|scene
构图歪斜|tilted horizon|地平线倾斜|cond
风格混杂|mixed styles|风格打架|scene
塑料感|plastic look|塑料质感|cond
现代元素|modern elements|穿帮现代物件|scene
恐怖元素|horror elements|血腥惊悚|scene
可识别车牌|readable license plate|车牌清楚|scene
"""


# ---------------------------------------------------------------- 第二批扩词（v1.1）
# 把代码侧 140 条补到文档全量：主题 40 / 构图 40 / 镜头 40 / 光线 40 / 风格 44 /
# 材质 40 / 画质 40 / 负面 40 = 324 条。与 `VISUAL-TERMS-v1.0.md` 逐行对应。
# v1.3（2026-11-20）在风格维增 `概念设定`，全量 325 条（风格 45）——词表外样本就此清零。
_TERM_DATA_V11 = {
    "subject": """
单人半身像|half-body portrait|半身人像,半身照|AV PS
全身人像|full-body portrait|全身照,立绘|AV IL
双人|two people|两人,对谈|MK IL
群体|group of people|一群人,人群|MK CD
背影|seen from behind|背对镜头|IL CD
剪影|silhouette|暗部剪影|PS CD
儿童|child|小孩,孩童|MK IL
老人|elderly person|长者|MK IL
宠物|pet|猫狗,萌宠|MK AV
野生动物|wild animal|野兽|IL CD
婴儿|baby|新生儿|AV
学生|student|校园人物|MK IL
厨师|chef|后厨人物|MK
团队群像|team group photo|团队合影|MK
双人合影|couple portrait|情侣合影|AV MK
面部特写|face close-up|脸部特写|AV
手部特写|hand detail|手持,握持|EC
行走|walking|步行,走动|MK CD
奔跑|running|跑步|MK PS
坐姿|seated|端坐,坐着|MK IL
俯身|leaning forward|前倾|MK EC
伸手|reaching out|伸手取物|MK EC
回头|looking back over shoulder|回眸|AV IL
交谈|talking with each other|对话,交流|MK IL
工作状态|working|工位,办公中|MK PS
阅读|reading|看书|MK IL
骑行|cycling|骑车|CD MK
悬浮|floating|漂浮|EC PS
产品静物|product still life|静物,单品|EC
食物特写|food close-up|菜品特写|MK EC
植物特写|botanical close-up|绿植,花草|MK EC
建筑外观|building exterior|外立面|PS CD
室内空间|interior space|内景|CD PS
风景|landscape|风光,自然景观|CD MK
载具|vehicle|车辆,交通工具|MK CD
机器人|robot|机械体|CD AV
图标组|icon set|图标组,ICON|AV PS
界面稿|UI mockup|界面稿,UI 稿|AV PS
抽象几何|abstract geometry|几何体|PS CD
环境空镜|empty scene|无人场景,空镜|PS CD
""",
    "composition": """
广角透视|wide-angle perspective|广角拉伸|CD PS
长焦压缩|telephoto compression|背景压缩|AV MK
重复韵律|repeating pattern|阵列,韵律|PS CD
三角形构图|triangular composition|三角稳定|PS CD
放射构图|radial composition|中心放射|PS CD
水平线构图|horizontal-line composition|横平构图|CD
垂直线构图|vertical-line composition|竖直构图|PS CD
曲线构图|curved-line composition|弧线构图|IL CD
单点透视|one-point perspective|一点透视|CD PS
等距视角|isometric viewpoint|等轴视角|IL PS
微距视角|macro viewpoint|超近距离|EC
第一人称视角|first-person view|POV 视角|CD
俯角 45 度|45-degree high angle|四十五度俯拍|EC MK
贴地视角|ground-level view|地面视角|CD MK
阶梯层次|stepped layers|层层递进|CD PS
边缘留白|edge margins|四周留白|EC AV
""",
    "lens": """
远景|long shot|大远景,wide shot|CD MK
全景|full shot|全景别|MK CD
中景|medium shot|中景别|MK CD PS
近景|close shot|近景别|AV EC
特写|close-up|特写镜头|EC AV
大特写|extreme close-up|微特写|EC AV
半身景|half shot|半身景别|AV
全身景|full-body shot|全身构图|IL AV
环境肖像|environmental portrait|场景人像|MK
过肩镜头|over-the-shoulder shot|越肩视角|CD
荷兰角|Dutch angle|倾斜构图,歪镜头|CD
鱼眼镜头|fisheye lens|球形镜头|CD
标准镜头|standard lens|常规镜头|MK AV
35mm 镜头|35mm lens|三五镜头|MK CD
50mm 镜头|50mm lens|五零镜头|AV MK
85mm 镜头|85mm lens|人像镜头|AV
135mm 镜头|135mm lens|中长焦|AV
200mm 长焦|200mm telephoto|长焦镜头|CD
24mm 广角|24mm wide|二四广角|CD PS
16mm 超广角|16mm ultra-wide|超广角镜头|CD
移轴镜头|tilt-shift lens|移轴|CD PS
微距镜头|macro lens|微距头|EC
变形宽银幕|anamorphic widescreen|宽银幕镜头|CD
定焦镜头|prime lens|定焦|AV EC
变焦镜头|zoom lens|变焦|MK
中画幅|medium format|中画幅相机|EC AV
大光圈 f/1.4|wide aperture f/1.4|大光圈|AV EC
小光圈 f/11|small aperture f/11|小光圈|CD EC
高速快门 1/1000s|high-speed shutter|凝固快门|MK CD
慢门 1/15s|slow shutter|慢速快门,拖影|CD
长曝光|long exposure|长曝|CD
手持纪实|handheld documentary|手持跟拍|MK CD
航拍|aerial photography|无人机视角|CD PS
水下摄影|underwater photography|水中拍摄|CD
全景接片|panoramic stitch|接片,宽幅拼接|CD PS
延时摄影|time-lapse|延时|CD
监控视角|security-camera view|摄像头视角|CD
手机视角|phone-camera look|手机拍摄|MK
复古镜头|vintage lens|老镜头,柔光老镜|CD AV
四分之三侧脸|three-quarter face|侧脸 45 度|AV
""",
    "lighting": """
颗粒氛围|grainy atmosphere|颗粒感|CD IL
三点布光|three-point lighting|三灯布光,标准布光|EC AV
美人碟光|beauty dish|雷达罩|AV
柔光箱|softbox lighting|柔光罩|EC AV
反光板补光|bounce fill|补光板|EC
阴天散射光|overcast diffused light|阴天光,散射光|MK CD
路灯照明|street lamp glow|路灯,街灯|CD
车灯照明|car headlight glow|车灯,头灯|CD
屏幕光|screen glow|屏幕反光,显示器光|CD MK
火光|firelight|火焰光,炉火光|IL CD
舞台追光|stage spotlight|追光,聚光灯|PS CD
直闪|direct flash|闪光灯直打,硬闪|MK CD
漏光光斑|light leak|漏光,胶片漏光|IL PS
冷调月光|cool moonlight|月光,冷月|IL CD
暖调夕照|warm sunset glow|夕阳光,暖黄光|MK CD
双色温对比|mixed color temperature|冷暖对撞|CD PS
""",
    "style": """
丙烯|acrylic painting|丙烯画|IL
版画|printmaking|木刻版画|IL PS
构成主义|constructivism|俄国构成,几何海报|PS
装饰艺术|Art Deco|装饰风,金属线条|PS CD
2.5D 插画|2.5D illustration|伪立体插画|IL AV
蓝晒|cyanotype|蓝晒法,普鲁士蓝|IL PS
双重曝光|double exposure|叠影|IL PS
纸雕|paper cut-out|剪纸,纸片层叠|IL PS
彩铅|colored pencil|彩色铅笔|IL
美漫线条|American comic inking|美漫风,硬线条|IL
法式漫画|bande dessinée|欧漫,法漫|IL
线稿上色|line art with color|线稿,描线上色|IL AV
霓虹插画|neon illustration|霓虹线稿,荧光线条|PS CD
玻璃拟态|glassmorphism|毛玻璃界面风|PS AV
柔焦朦胧|soft-focus haze|柔焦,朦胧感|AV IL
产品爆炸图|exploded product view|结构爆炸图|EC CD
""",
    "texture": """
高光烤漆|glossy lacquer|亮面烤漆|EC MK
玻璃|glass|透明玻璃|EC PS
灰尘|dust particles|浮尘|CD
细腻纹理|fine texture|细纹理,微纹理|EC CD
磨砂金属|matte metal|喷砂金属|EC AV
高光金属|polished metal|抛光金属|EC CD
不锈钢|stainless steel|钢质|EC
铝合金|aluminum alloy|铝材|EC
亚克力|acrylic|有机玻璃|EC PS
硅胶|silicone|软胶|EC
橡胶|rubber|橡胶质感|EC CD
漆皮|patent leather|亮面皮|EC AV
天鹅绒|velvet|丝绒|AV PS
牛仔布|denim|丹宁|MK AV
针织|knitwear|毛线,针织纹理|MK EC
纸张|paper|纸质感|PS IL
牛皮纸|kraft paper|牛皮纸质|PS MK
石膏|plaster|石膏白模|CD PS
玻璃纤维|fiberglass|玻纤|CD EC
石材|stone|天然石|CD PS
""",
    "quality": """
8K|8K resolution|8K 分辨率,超高清|EC CD
HDR|high dynamic range|高动态范围|CD PS
色彩分级|color grading|调色,色阶统一|CD PS
产品级布光|product lighting|产品光|EC
PBR 材质|PBR material|物理渲染材质|EC CD
抗锯齿|anti-aliasing|边缘平滑|AV PS
广色域|wide color gamut|色域广|PS EC
边缘锐利|crisp edges|轮廓清晰|EC PS
16bit 色深|16-bit color depth|高位深|PS CD
高对比|high contrast|强对比|CD PS
高饱和|high saturation|高彩度,浓色|MK IL
单色调|monochrome|同色系|PS CD
双色调|duotone|双色版|PS IL
暗部通透|clean shadows|暗部细节|CD
中性灰背景|neutral gray background|灰底|EC AV
印刷网点|halftone dots|网点|PS IL
色差校正|chromatic correction|紫边校正|CD
轻微柔化|subtle softening|柔化处理|AV IL
清晰层次|clear tonal layers|层次分明|CD PS
无损锐化|unsharp mask|USM 锐化|EC
抖动降噪|dithering|抖动处理|PS
伽马校正|gamma correction|伽马|PS EC
无压缩伪影|no compression artifacts|无压缩块|MK EC IL AV PS CD
白平衡准确|accurate white balance|色温准确|EC MK
""",
}

_NEG_DATA_V11 = """
塑料皮肤|plastic skin|假脸,油光脸|person
皮肤比例错误|wrong skin proportions|身材比例失调|person
说明文字|caption text|角标文案|scene
水印边框|watermark border|边框水印|scene
空白过多|excessive empty space|太空,内容不足|cond
强行 HDR|overprocessed HDR|假 HDR|cond
低多边形伪影|low-poly artifacts|块面破碎|cond
拼贴接缝|collage seams|拼接痕迹|cond
过时滤镜|dated filter|土味滤镜|cond
真人可识别肖像|identifiable real person|真人正脸|safety
商标复刻|trademark reproduction|复刻商标|safety
暴力血腥|gore and violence|血腥画面|safety
裸露|nudity|裸露画面|safety
"""


def _parse_rows(block: str, fields: int = 4) -> tuple:
    rows = []
    for line in block.strip().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = [p.strip() for p in line.split("|")]
        while len(parts) < fields:
            parts.append("")
        zh, en = parts[0], parts[1]
        aliases = tuple(a for a in parts[2].replace("，", ",").split(",") if a)
        rest = parts[3]
        rows.append((zh, en, aliases, rest))
    return tuple(rows)


_MERGED_TERM_DATA: dict[str, str] = dict(_TERM_DATA)
for _dim, _block in _TERM_DATA_V11.items():
    _MERGED_TERM_DATA[_dim] = _MERGED_TERM_DATA.get(_dim, "") + "\n" + _block

TERMS = {dim: _parse_rows(block) for dim, block in _MERGED_TERM_DATA.items()}
NEGATIVE_TERMS = tuple(
    (zh, en, aliases, level)
    for zh, en, aliases, level in (_parse_rows(_NEG_DATA) + _parse_rows(_NEG_DATA_V11))
)
# 词表规模自检用（文档口径 325 条）；测试与基准脚本都读这个数
TERM_COUNT = sum(len(rows) for rows in TERMS.values()) + len(NEGATIVE_TERMS)

# ---------------------------------------------------------------- 口语别名（召回层）
# 语料 `IMAGE-CORPUS-v0.1.md` 用的是真人说法（「黄昏」「压扁」「性冷淡」），
# 词典必须能接住，否则召回永远卡在术语层。别名只影响召回，输出仍用主词。
_ALIAS_EXTRA: dict[str, tuple[str, ...]] = {
    # 风格
    "商业产品摄影": ("产品图", "护肤品", "化妆品", "瓶身特写", "简洁商务摄影"),
    "极简主义": ("高级感", "性冷淡", "极简", "简洁风"),
    "电影感": ("老电影", "电影质感", "电影风格"),
    "胶片摄影": ("底片", "老照片", "年代感", "怀旧", "复古胶片"),
    # 映射表里被当成「风格」写的光线/画质/镜头词：同义挂到真实维度，避免风格槽硬接
    "纪实摄影": ("真实场景", "生活方式摄影"),
    "油画": ("古典油画",),
    "无缝背景": ("白底无缝背景",),
    "时尚大片": ("杂志封面", "时尚图", "大片感"),
    "玻璃拟态": ("未来科技", "科技感", "通透界面"),
    "水墨": ("古风", "写意"),
    "国潮插画": ("国风", "古装", "文创"),
    "3D 渲染": ("3D 形象", "三维形象", "立体形象"),
    "低多边形": ("卡通", "卡通一点"),
    "波普艺术": ("涂鸦", "街头感"),
    "拼贴": ("剪贴", "拼贴画"),
    "复古海报": ("复古", "老海报"),
    # 镜头
    "微距镜头": ("看清纹理", "材质纹理", "近摄", "微距"),
    "85mm 镜头": ("人像", "虚化背景"),
    "长焦压缩": ("长焦", "压扁", "背景压扁"),
    "135mm 镜头": ("长焦人像",),
    "广角透视": ("广角", "显空间大"),
    "24mm 广角": ("广角镜头",),
    "航拍": ("无人机", "aerial"),
    "鸟瞰": ("俯拍全貌", "顶拍"),
    "仰视": ("从下往上", "低角度", "仰拍"),
    "贴地视角": ("贴地", "低机位"),
    "荷兰角": ("倾斜", "歪一点"),
    "全景接片": ("接片", "宽幅", "拼接"),
    "平铺构图": ("平铺", "摆盘", "俯拍平铺"),
    "手机视角": ("手机拍", "随手拍"),
    "全景": ("全景别", "宽景"),
    # 光线
    "黄金时刻": ("黄昏", "日落", "夕阳", "太阳落山"),
    "低调": ("压暗", "一盏灯", "台灯", "昏暗", "夜里", "暗调低调"),
    "自然光": ("暖调自然光",),
    "霓虹光": ("霓虹", "霓虹灯"),
    "影棚布光": ("影棚", "棚拍", "均匀干净的光", "影棚柔光"),
    "柔光": ("柔和光", "软光"),
    "硬光": ("强光",),
    "明暗对比": ("阴影重", "强对比", "光比大"),
    "轮廓光": ("边缘发光", "边缘光"),
    "烛光": ("晚餐", "烛火"),
    "柔光箱": ("柔光罩", "打光箱"),
    "反光板补光": ("反光板", "补光板"),
    "直闪": ("强闪", "闪电一样", "硬闪"),
    "三点布光": ("三点光", "三灯"),
    "体积光": ("一束束光", "光束", "森林光"),
    "阴天散射光": ("阴天", "散射", "不要硬阴影"),
    "窗光": ("窗户光", "窗边光", "窗户自然光"),
    "双色温对比": ("冷暖对比", "冷暖"),
    "高调": ("明亮", "干净明亮"),
    "蓝调时刻": ("傍晚", "天没全黑", "冷蓝"),
}


def _with_extra_aliases(rows: tuple) -> tuple:
    out = []
    for zh, en, aliases, rest in rows:
        extra = _ALIAS_EXTRA.get(zh, ())
        out.append((zh, en, tuple(dict.fromkeys(aliases + extra)), rest))
    return tuple(out)


TERMS = {dim: _with_extra_aliases(rows) for dim, rows in TERMS.items()}
NEGATIVE_TERMS = _with_extra_aliases(NEGATIVE_TERMS)

TERM_INDEX: dict[str, tuple[str, str]] = {}
for _dim, _rows in TERMS.items():
    for _zh, _en, _aliases, _scenes in _rows:
        TERM_INDEX.setdefault(_zh, (_dim, _en))
        for _a in _aliases:
            TERM_INDEX.setdefault(_a, (_dim, _en))
for _zh, _en, _aliases, _level in NEGATIVE_TERMS:
    TERM_INDEX.setdefault(_zh, ("negative", _en))
del _dim, _rows, _zh, _en, _aliases, _scenes, _a, _level, _block, _MERGED_TERM_DATA


def _build_canon() -> dict[str, str]:
    """所有写法（主词/别名/英文/负面词）→ 引擎主词。

    禁配表用的是文档用语（「卡通」「霓虹」），需要先归一到引擎词才能从段落里清除。
    """
    canon: dict[str, str] = {}
    for rows in TERMS.values():
        for zh, en, aliases, _scenes in rows:
            canon.setdefault(zh.lower(), zh)
            canon.setdefault(en.lower(), zh)
            for alias in aliases:
                canon.setdefault(alias.lower(), zh)
    for zh, _en, aliases, _level in NEGATIVE_TERMS:
        canon.setdefault(zh.lower(), zh)
        for alias in aliases:
            canon.setdefault(alias.lower(), zh)
    return canon


TERM_CANON = _build_canon()


def to_en(term: str) -> str:
    """术语 → 英文写法；未收录的词原样返回（v1 不做翻译，见计划 §6 风险表）。"""
    entry = TERM_INDEX.get(term)
    return entry[1] if entry else term


# ---------------------------------------------------------------- 场景/比例/平台判定
def pick_scene(text: str) -> str:
    lowered = text.lower()
    for word, scene in SCENE_KEYWORDS:
        if word in lowered:
            return scene
    return DEFAULT_SCENE


def pick_ratio(text: str, scene: str, default: str | None = None) -> str:
    m = RATIO_RE.search(text)
    if m:
        ratio = f"{int(m.group(1))}:{int(m.group(2))}"
        if ratio in RATIOS:
            return ratio
    for word, ratio in RATIO_WORDS:
        if word in text:
            return ratio
    return default or RATIO_DEFAULT.get(scene, "1:1")


def pick_platform(value: object) -> str:
    key = str(value or "").strip().lower()
    return PLATFORM_ALIAS.get(key, "generic")


# ---------------------------------------------------------------- 词条命中
def match_terms(text: str, scene: str) -> dict[str, str]:
    """按维度取权重最高的一条：场景吻合 1.0，跨场景 0.7，同分时取更长的词。"""
    hits: dict[str, str] = {}
    # 调用方通常已 lower 过输入，但词表主词本身可能带大写拉丁字母（「3D 渲染」「2.5D 插画」），
    # 直接拿主词比对会永不命中，这里统一在 lower 后的文本上比。
    haystack = text.lower()
    for dim, rows in TERMS.items():
        best: tuple[float, int, str] | None = None
        for zh, en, aliases, scenes in rows:
            # 英文输入时按英文写法命中（v1 不做翻译，只做同形匹配）
            words = (zh, *aliases) + ((en.lower(),) if len(en) > 3 else ())
            if not any(w.lower() in haystack for w in words):
                continue
            weight = 1.0 if (not scenes or scene in scenes) else 0.7
            # 最长匹配优先（规范 §3 第 1 条）：比的是**命中的写法**有多长，不是主词有多长——
            # 否则「复古胶片」（胶片摄影的别名）会被另一个词更短的别名「复古」抢走。
            hit_len = max(len(word) for word in words if word.lower() in haystack)
            candidate = (-hit_len, -weight, zh)
            if best is None or candidate < best:
                best = candidate
        if best:
            hits[dim] = best[2]
    return hits


def match_negative(level: str) -> list[str]:
    return [zh for zh, _en, _aliases, lv in NEGATIVE_TERMS if lv == level]


BASE_NEGATIVE = match_negative("base")
PERSON_NEGATIVE = match_negative("person")
COND_NEGATIVE = match_negative("cond")

# 人物负面分三档：核心 3 条必带，手部/皮肤类只在文本提到时才追加。
# 盲评把「12 条负面全塞」判为冗余（无冗余 3.57，全场最低），这里是针对性收敛。
PERSON_CORE_NEGATIVE = ("多余肢体", "面部崩坏", "扭曲手部")
HAND_NEGATIVE = ("多余手指", "缺失手指")
SKIN_NEGATIVE = ("过度磨皮", "塑料皮肤", "皮肤比例错误")
SKIN_HINTS = ("皮肤", "光滑", "美颜", "磨皮", "质感细腻")

# 插画/3D 类媒介：不能套「质感真实」这种摄影向限定句
ILLUSTRATION_STYLES = {
    "扁平插画", "矢量插画", "等距插画", "3D 渲染", "黏土动画", "像素艺术", "水彩",
    "油画", "素描", "水墨", "国潮插画", "日式动画赛璐璐", "低多边形", "波普艺术",
    "版画", "丙烯", "2.5D 插画", "彩铅", "美漫线条", "法式漫画", "线稿上色",
    "霓虹插画", "纸雕", "拼贴", "蓝晒", "微缩模型", "玻璃拟态", "柔焦朦胧",
    "产品爆炸图", "建筑效果图",
}

# 场景追加负面（规范 §4 矩阵最后一列）
SCENE_NEGATIVE = {
    "MK": ("主体裁切",),
    "EC": ("过曝", "主体裁切"),
    "IL": ("签名", "风格混杂"),
    "AV": (),
    "PS": ("主体压字", "边缘裁切"),
    "CD": ("现代元素", "风格混杂"),
}

# 不能用裸「人」：像「别太吓人」这样的口语会误触发肢体负面词
PERSON_WORDS = ("人物", "人像", "人形", "人群", "人们", "行人", "路人", "男人", "女人",
                "男孩", "女孩", "小孩", "儿童", "老人", "婴儿", "宝宝", "年轻人", "背影",
                "角色", "头像", "主播", "骑手", "程序员", "厨师", "学生", "团队", "模特",
                "手部", "双手", "手指", "猫", "狗", "宠物")
_PERSON_RE = re.compile(r"[一二三四五六七八九十几\d]\s*[个位名]\s*人")

# ---------------------------------------------------------------- 口径转译
# 方案文档的口语映射：形容词不可执行，必须转成可命中的术语。
SPOKEN_MAP = {
    "燃": ("lighting", "硬光"),
    "硬核": ("lighting", "硬光"),
    "压迫感": ("lighting", "低调"),
    "治愈": ("lighting", "柔光"),
    "温柔": ("lighting", "柔光"),
    "清爽": ("lighting", "自然光"),
    "高级感": ("style", "极简主义"),
    "未来感": ("lighting", "霓虹光"),
    "不死板": ("composition", "上方留白"),
    "复古": ("style", "胶片摄影"),
    "国风": ("style", "国潮插画"),
    "赛博": ("style", "赛博朋克"),
}

# 领域 → (首选风格, 禁配词)：与 analyzer.DOMAIN_KEYWORDS 的 22 个领域一一对应。
# 禁配列与 `DOMAIN-STYLE-MAP-v0.1.md` §2「禁配」**逐字一致**（有测试守着），
# 因此不只是风格维词：光线（低调）、镜头（鱼眼镜头）、材质（做旧）、负面（恐怖元素）都在里面。
# 首选列是「风格维投影」：文档推荐列里有非风格维词（影棚柔光/对称构图/食物特写），
# 填不进 S5，这里取语义最近的风格词，避免用光线词占风格槽。
_DOMAIN_STYLE_DATA = """
energy|建筑效果图|蒸汽朋克,低多边形,恐怖元素
tech|极简主义|油画,水彩,做旧
marketing|时尚大片|黑白摄影,做旧,低饱和
ecommerce|商业产品摄影|杂乱背景,纪实抓拍,赛博朋克
education|扁平插画|赛博朋克,恐怖元素,低饱和暗调
finance|极简主义|赛博朋克,蒸汽朋克,波普艺术
medical|写实摄影|血腥,解剖,恐怖元素,低多边形
legal|极简主义|赛博朋克,涂鸦,拼贴
game|赛博朋克|白底产品图,商务极简
hr|写实摄影|暗调低调,恐怖,做旧
manufacturing|纪实摄影|水彩,毛绒,纸雕
auto|商业产品摄影|卡通,像素艺术,塑料感
travel|纪实摄影|赛博朋克,恐怖,混凝土工业
food|商业产品摄影|赛博朋克,黑白摄影,塑料感
realestate|建筑效果图|鱼眼镜头,荷兰角,恐怖元素
research|极简主义|时尚大片,波普艺术,霓虹光
security|极简主义|恐怖元素,血腥,恐怖谷人脸
logistics|纪实摄影|水彩,毛绒,装饰艺术
government|极简主义|赛博朋克,涂鸦,恐怖,波普
service|扁平插画|低调暗调,硬光,恐怖
agriculture|纪实摄影|赛博朋克,玻璃拟态,霓虹
media|电影感|白底产品图,扁平插画,图标组
general|写实摄影|
"""
DOMAIN_STYLE: dict[str, tuple[str, tuple[str, ...]]] = {}
for _line in _DOMAIN_STYLE_DATA.strip().splitlines():
    _d, _pref, _ban = [p.strip() for p in _line.split("|")]
    DOMAIN_STYLE[_d] = (_pref, tuple(b for b in _ban.split(",") if b))
del _line, _d, _pref, _ban

DOMAIN_BAN: dict[str, tuple[str, ...]] = {d: ban for d, (_pref, ban) in DOMAIN_STYLE.items()}

# 文档禁配列里的复合并列/简称写法 → 引擎词：文档写「暗调低调」，引擎词是「低调」；
# 不映射的（「白底产品图」「商务极简」）按原样匹配输入，避免把「白底」「极简」一律当禁配。
_BAN_FORM_EXTRA: dict[str, tuple[str, ...]] = {
    "暗调低调": ("低调", "暗调"),
    "低调暗调": ("低调", "暗调"),
    "低饱和暗调": ("低饱和", "低调"),
    "恐怖": ("恐怖元素",),
    "混凝土工业": ("混凝土",),
    "纪实抓拍": ("纪实摄影",),
    "白底产品图": ("白底图",),
}


def ban_forms(term: str) -> tuple[str, ...]:
    """禁配词的命中形式：文档写法 + 引擎主词 + 英文写法 + 复合写法的拆分形式（去重保序）。"""
    forms = [term]
    canon = TERM_CANON.get(term.lower())
    if canon:
        forms.append(canon)
        entry = TERM_INDEX.get(canon)
        if entry and len(entry[1]) > 3:      # 英文输入（"cyberpunk"）也要接住
            forms.append(entry[1].lower())
    forms.extend(_BAN_FORM_EXTRA.get(term, ()))
    return tuple(dict.fromkeys(forms))


def banned_hits(text: str, domain: str) -> list[tuple[str, tuple[str, ...]]]:
    """返回该领域禁配词在 text 里的命中：[(文档写法, 命中形式)]，按表内顺序。

    判据从「匹配到的风格词是否在 ban 列表」改成「输入是否命中禁配词」——
    这样「鱼眼镜头」（lens）、「杂乱背景」（负面）、「暗调低调」（光线）也能被接住。
    """
    lowered = text.lower()
    hits: list[tuple[str, tuple[str, ...]]] = []
    for term in DOMAIN_BAN.get(domain, ()):
        forms = ban_forms(term)
        if any(form.lower() in lowered for form in forms):
            hits.append((term, forms))
    return hits


# 领域 → 灰区风格（映射表第 4 列）：该领域内「有条件才成立」的风格，保留但要说清条件。
#   q = 限定词必须补进正文，否则组合自相矛盾（「电影感」不限定就成了高对比大片）
#   c = 只是适用条件，补进正文会变成怪句子（「像素艺术，仅年轻向活动」），故只作提示
# 文案与 DOMAIN-STYLE-MAP-v0.1.md §2 括号内容逐字一致，改表即改这里（有测试守着）。
_GRAY_DATA = """
energy|电影感|q|克制调色
tech|赛博朋克|q|企业级、非废土
marketing|像素艺术|c|仅年轻向活动
ecommerce|微缩模型|c|创意主图
education|日式动画赛璐璐|c|K12 适用，成人培训慎用
finance|电影感|q|稳重、不高对比
medical|微距|q|仅器械细节，不涉人体
legal|古典油画|c|仅「厚重感」隐喻
game|水墨|c|国风游戏
hr|电影感|c|招聘品牌片
manufacturing|赛博朋克|c|智能工厂
auto|复古胶片|c|经典车
travel|国潮插画|c|文创周边
food|暗调低调|c|高端餐饮
realestate|黄金时刻|q|真实交付感
research|蓝晒|c|历史感论文配图
security|赛博朋克|c|攻防演示，非犯罪美化
logistics|硬光|c|仓储工业感
government|国潮插画|c|节庆宣传
service|日式动画|c|年轻客群
agriculture|胶片颗粒|c|乡土叙事
media|赛博朋克|c|题材相关
"""
DOMAIN_STYLE_GRAY: dict[str, dict[str, tuple[str, str]]] = {}
for _line in _GRAY_DATA.strip().splitlines():
    _d, _term, _mode, _note = [p.strip() for p in _line.split("|")]
    DOMAIN_STYLE_GRAY.setdefault(_d, {})[_term] = (_mode, _note)
del _line, _d, _term, _mode, _note

# ---------------------------------------------------------------- 安全
# 红线：直接拦截（不写进负面词，理由见规范 §8）。
SAFETY_BLOCK = ("血腥", "暴力", "裸露", "色情", "仇恨", "纳粹", "虐待", "自杀", "恐怖袭击")
# 软红线：改写主体并记 warning，不拦截。
SAFETY_SOFT = {
    "明星": "可识别真人", "网红": "可识别真人", "真人": "可识别真人",
    "商标": "商标", "复刻 logo": "商标", "品牌标识": "商标",
    "漫威": "版权角色", "迪士尼": "版权角色", "宝可梦": "版权角色",
    "奥特曼": "版权角色", "皮卡丘": "版权角色",
}

# ---------------------------------------------------------------- 主体抽取
_LEADING = ("请帮我", "帮我", "请", "麻烦", "给我", "能不能", "可以", "我想", "我要",
            "想要", "生成一张", "生成", "做一张", "做张", "来一张", "出一张",
            "画一张", "画一幅", "画一只", "画个", "画", "设计一张", "设计", "出图")
_TRAILING = ("的宣传图", "的配图", "的白底主图", "的海报", "的主图", "的封面", "的头像",
             "的概念图", "的插画", "的图片", "的图", "宣传图", "营销图", "推广图", "配图",
             "海报", "白底图", "主图", "封面", "头像", "概念图", "插画", "图片", "图像",
             "壁纸", "立绘", "主视觉", "展板", "详情页")
_LEADING_SORTED = tuple(sorted(_LEADING, key=len, reverse=True))
_TRAILING_SORTED = tuple(sorted(_TRAILING, key=len, reverse=True))
# 诉求句：描述「要什么效果」，不是主体本身
_DEMAND_RE = re.compile(r"^(要|想|希望|需要|别|不要|有点|保持|尽量|让人|显得|看上去|风格|留出|预留|避免|去掉|加上)")
# 显式主体句：「画面是 X」「主体是 X」优先于任何其它子句
_EXPLICIT_RE = re.compile(r"^(画面是|画面为|主体是|主体为|内容是|内容为|主角是)")
# 比例/版式词：比例是画幅属性，不是主体（「做一张 9:16 竖版海报」的主体是海报，不是 9:16）
_RATIO_PREFIX = re.compile(r"^\d+\s*[:：比]\s*\d+\s*(竖版|横版|方版|竖屏|横屏|版|尺寸|画幅)?")


def extract_subject(text: str, limit: int = 30) -> str:
    """从原话里剥掉「帮我/做一张/…的宣传图」这类壳，剩下的当主体。

    先按标点切子句并跳过「要有压迫感」这类诉求句（它们描述效果而非主体），
    再剥前缀动词与后缀产物词；全剥空时退回原始子句，宁可保守也不产出空主体。
    """
    raw = " ".join(text.split())
    clauses = [c.strip(" 的，,、") for c in re.split(r"[，。；;！!？?\n]", raw) if c.strip()]
    target = raw
    candidates: list[str] = []
    for clause in clauses:                      # 「画面是 X」最可靠，优先采信
        if _EXPLICIT_RE.match(clause):
            target = _EXPLICIT_RE.sub("", clause)
            candidates = [target]
            break
    else:
        candidates = [c for c in clauses if not _DEMAND_RE.match(c)]   # 跳过诉求句
        target = candidates[0] if candidates else raw

    for candidate in candidates:
        body = _strip_shell(candidate)
        if not body:                            # 剥空说明这句全是壳，换下一句再试
            continue
        if _is_term_only(body):                 # 「赛博朋克风格」是文风描述，不是主体
            continue
        return body[:limit]
    return ""


# 可做谓语但不能当主体的维度词（风格/光线/构图/材质/画质）
_NON_SUBJECT_TERMS = {zh for dim, rows in TERMS.items() if dim != "subject"
                      for zh, _en, _aliases, _scenes in rows}


def _is_term_only(body: str) -> bool:
    """整段只是某个维度术语（允许带「风格/质感/效果/氛围」后缀），则不是主体。"""
    bare = re.sub(r"(风格|质感|效果|氛围|感)$", "", body).strip()
    return bare in _NON_SUBJECT_TERMS or body in _NON_SUBJECT_TERMS


def _strip_shell(target: str) -> str:
    """剥掉前缀动词、后缀产物词与比例词；剥空返回空串，由调用方决定退路。"""
    body = re.sub(r"^(给|为)(这|那)?[篇个部条张]?", "", target)
    changed = True
    while changed:
        changed = False
        for word in _LEADING_SORTED:
            if body.startswith(word):
                body = body[len(word):].lstrip("，,：:、 ")
                changed = True
    for word in _TRAILING_SORTED:
        if body.endswith(word):
            body = body[: -len(word)].rstrip("，, 的")
            break
    body = re.split(r"[，。；;！!？?\n]", body)[0].strip(" 的，,、")
    # 「做一张9:16竖版海报」剥掉产物词后只剩比例词，不能当主体
    return _RATIO_PREFIX.sub("", body).strip(" 的，,、")


def has_person(text: str) -> bool:
    return any(w in text for w in PERSON_WORDS) or bool(_PERSON_RE.search(text))


def check_safety(text: str) -> tuple[list[str], list[dict]]:
    """返回 (拦截词, 软红线提示)。拦截词非空时由 pipeline 抛 SAFETY_BLOCKED。"""
    lowered = text.lower()
    blocked = [w for w in SAFETY_BLOCK if w in lowered]
    soft = [{"word": w, "type": why} for w, why in SAFETY_SOFT.items() if w in lowered]
    return blocked, soft
