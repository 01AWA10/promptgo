# 视觉术语表 v0.1

> 阶段 1 交付物 · 2026-11-14 · 关联：[`../IMAGE-PROMPT-ITERATION-PLAN.md`](../IMAGE-PROMPT-ITERATION-PLAN.md)
> 定位：8 类初稿，每类 ≥20 条，供阶段 2 结构设计与阶段 3 词表扩写使用；v0.1 不追求穷举，追求**分类无歧义、可映射、可回归**。

## 1. 使用规则

1. **每维上限**：同一维度最多 3 个词；主风格 1 个 + 辅助 1 个，避免风格打架。
2. **顺序**：主体 → 场景 → 构图/视角 → 光线 → 风格 → 材质 → 技术 → 负面。
3. **长词优先、命中不重叠**：与现有渠道/语气匹配一致（「侧逆光」不得被「逆光」抢先）。
4. **同义去重**：一个概念只保留一个主词，别名进 `aliases`，输出时取命中优先级最高的。
5. **冲突需显式标注**：如「写实摄影 + 卡通渲染」「极简 + 繁复纹理」「高调 + 低调」，检测到即降权并要求用户确认（阶段 3 实现）。
6. **安全优先**：不输出在世艺术家姓名、工作室/品牌名、商标与版权角色，见第 11 节替换表。
7. **平台语法**：SDXL 可用权重 `(term:1.2)`；MJ 用自然语言 + `--ar`；Flux/DALL·E 3 用自然语言，不加参数。

## 2. 总览

| 编号 | 类别 | 条目数 | 主要用途 |
| --- | --- | --- | --- |
| T1 | 主体与动作 | 24 | 明确「画什么、在做什么」 |
| T2 | 构图与视角 | 22 | 决定画面组织与观看位置 |
| T3 | 景别与镜头 | 22 | 控制取景范围与镜头语言 |
| T4 | 光线与氛围 | 24 | 决定情绪与立体感 |
| T5 | 风格与媒介 | 28 | 决定「像什么」：摄影/插画/3D/流派 |
| T6 | 材质与细节 | 22 | 提升真实度与触感 |
| T7 | 画质与技术 | 22 | 控制清晰度、后期与成片质感 |
| T8 | 负面约束 | 24 | 排除常见崩坏与合规风险 |

## 3. T1 主体与动作（24）

| 中文 | 英文 | 说明 / 搭配 |
| --- | --- | --- |
| 单人 | single person | 默认主体；头像/人设常用 |
| 双人 | two people | 注意互动关系与站位 |
| 群体 | group of people | 需限定人数范围，避免脸崩 |
| 半身人像 | half-body portrait | 头像、人物介绍 |
| 全身人像 | full-body portrait | 服装展示、角色立绘 |
| 背影 | seen from behind | 叙事感强，避免面部细节 |
| 剪影 | silhouette | 逆光/极简构图 |
| 儿童 | child | 安全敏感，避免可识别真人 |
| 老人 | elderly person | 注意皮肤纹理自然 |
| 宠物 | pet | 猫/狗需指定品种或形态 |
| 行走 | walking | 动态抓拍感 |
| 奔跑 | running | 配合快门感 |
| 坐姿 | seated | 室内、阅读、咖啡场景 |
| 俯身 | leaning forward | 互动、工作场景 |
| 伸手 | reaching out | 强调动作方向 |
| 回头 | looking back over shoulder | 叙事与情绪 |
| 交谈 | talking with each other | 双人/群体 |
| 工作状态 | working | 办公、工位、车间 |
| 阅读 | reading | 书卷气、安静 |
| 骑行 | cycling | 街头、运动 |
| 悬浮 | floating | 产品图、超现实 |
| 产品静物 | product still life | 电商主图基础 |
| 建筑外观 | building exterior | 房产、城市 |
| 室内空间 | interior space | 场景图、概念图 |

## 4. T2 构图与视角（22）

| 中文 | 英文 | 说明 / 搭配 |
| --- | --- | --- |
| 三分法 | rule of thirds | 通用，主体落在交点 |
| 中心构图 | centered composition | 产品、头像、海报主视觉 |
| 对称构图 | symmetrical composition | 建筑、古风、仪式感 |
| 对角线构图 | diagonal composition | 动态、张力 |
| 引导线 | leading lines | 道路、走廊、光束 |
| 框架构图 | framing | 门窗、拱廊取景 |
| 前景层次 | foreground layering | 增加空间深度 |
| 负空间 | negative space | 预留文案区，海报常用 |
| 黄金分割 | golden ratio | 比三分法更古典 |
| 重复韵律 | repeating pattern | 阵列、建筑立面 |
| 仰视 | low angle | 显高大、权威 |
| 俯视 | high angle | 显渺小、全局 |
| 平视 | eye level | 亲和、真实 |
| 鸟瞰 | bird's-eye view | 城市、展场全貌 |
| 广角透视 | wide-angle perspective | 空间拉伸，边缘畸变需注意 |
| 长焦压缩 | telephoto compression | 背景贴近主体，人像常用 |
| 浅景深 | shallow depth of field | 突出主体，虚化背景 |
| 深景深 | deep focus | 风景、建筑全清晰 |
| 极简构图 | minimalist composition | 大面积留白 |
| 满版构图 | full-bleed composition | 冲击力强，慎留字区 |
| 中心留空 | centered empty space | 促销海报、展板 |
| 版式留白 | layout whitespace | 与文字排版配合 |

## 5. T3 景别与镜头（22）

| 中文 | 英文 | 说明 / 搭配 |
| --- | --- | --- |
| 远景 | long shot | 交代环境 |
| 全景 | full shot | 人物全身 + 环境 |
| 中景 | medium shot | 半身到大腿 |
| 近景 | close shot | 胸部以上 |
| 特写 | close-up | 面部或产品局部 |
| 大特写 | extreme close-up | 材质、纹理、眼神 |
| 半身景 | half shot | 头像/人设标准 |
| 全身景 | full-body shot | 服装、角色 |
| 环境肖像 | environmental portrait | 人物 + 职业场景 |
| 过肩镜头 | over-the-shoulder shot | 分镜、对话 |
| 荷兰角 | Dutch angle | 不安、失衡感 |
| 鱼眼镜头 | fisheye lens | 夸张空间，慎用 |
| 标准镜头 | standard lens | 接近人眼，50mm 等效 |
| 35mm 镜头 | 35mm lens | 纪实、街拍 |
| 50mm 镜头 | 50mm lens | 自然人像 |
| 85mm 镜头 | 85mm lens | 人像压缩、虚化 |
| 135mm 镜头 | 135mm lens | 强压缩、背景极简 |
| 微距镜头 | macro lens | 产品细节、水珠 |
| 航拍 | aerial photography | 大场景、地形 |
| 水下摄影 | underwater photography | 蓝绿调、悬浮感 |
| 手持纪实 | handheld documentary | 轻微动态模糊 |
| 长曝光 | long exposure | 车流、水面丝滑 |

## 6. T4 光线与氛围（24）

| 中文 | 英文 | 说明 / 搭配 |
| --- | --- | --- |
| 自然光 | natural light | 通用，真实 |
| 黄金时刻 | golden hour | 日出后/日落前，暖调 |
| 蓝调时刻 | blue hour | 日落后，冷蓝 |
| 正午硬光 | harsh midday light | 强阴影，风格化 |
| 顺光 | front lighting | 平实、细节清楚 |
| 侧光 | side lighting | 立体、质感 |
| 逆光 | backlighting | 轮廓、剪影 |
| 侧逆光 | side-back lighting | 发丝光、氛围 |
| 顶光 | top lighting | 戏剧、压抑 |
| 底光 | under lighting | 恐怖、非自然 |
| 伦勃朗光 | Rembrandt lighting | 人像经典三角光 |
| 蝴蝶光 | butterfly lighting | 美妆、商业人像 |
| 柔光 | soft light | 产品、皮肤友好 |
| 硬光 | hard light | 强对比、街头 |
| 窗光 | window light | 室内、安静 |
| 霓虹光 | neon lighting | 赛博朋克、夜街 |
| 烛光 | candlelight | 温暖、私密 |
| 体积光 | volumetric light | 丁达尔、森林/舞台 |
| 轮廓光 | rim light | 分离主体与背景 |
| 高调 | high-key | 明亮、干净 |
| 低调 | low-key | 暗调、悬疑 |
| 明暗对比 | chiaroscuro | 强戏剧性 |
| 雾气 | atmospheric fog | 层次与距离感 |
| 颗粒氛围 | grainy atmosphere | 复古、胶片感 |

## 7. T5 风格与媒介（28）

| 中文 | 英文 | 说明 / 搭配 |
| --- | --- | --- |
| 写实摄影 | photorealistic photography | 通用底座 |
| 纪实摄影 | documentary photography | 真实、抓拍 |
| 商业产品摄影 | commercial product photography | 电商、广告 |
| 时尚大片 | fashion editorial | 强造型、强光比 |
| 电影感 | cinematic | 宽银幕、调色 |
| 胶片摄影 | film photography | 颗粒、暖调 |
| 黑白摄影 | black-and-white photography | 结构、质感 |
| 水彩 | watercolor | 晕染、留白 |
| 油画 | oil painting | 厚涂、笔触 |
| 丙烯 | acrylic painting | 色彩饱和、平涂感 |
| 素描 | pencil sketch | 线稿、结构 |
| 版画 | printmaking | 刀味、套色 |
| 水墨 | ink wash painting | 留白、墨韵 |
| 扁平插画 | flat illustration | 简洁、商用安全 |
| 矢量插画 | vector illustration | 边缘干净、可无限缩放 |
| 2.5D 插画 | 2.5D illustration | 伪立体、界面风 |
| 等距视角插画 | isometric illustration | 场景/流程示意 |
| 3D 渲染 | 3D render | 产品、IP 形象 |
| 黏土动画 | claymation | 手作、可爱 |
| 像素艺术 | pixel art | 复古游戏 |
| 赛博朋克 | cyberpunk | 霓虹、雨夜、科技 |
| 蒸汽朋克 | steampunk | 黄铜、齿轮、维多利亚 |
| 极简主义 | minimalism | 少元素、大留白 |
| 构成主义 | constructivism | 几何、红黑、海报感 |
| 装饰艺术 | Art Deco | 对称、金属线条 |
| 国潮插画 | Chinese-chic illustration | 传统元素 + 现代构成 |
| 日式动画赛璐璐 | anime cel shading | 二维动画上色 |
| 低多边形 | low poly | 几何切面、科技感 |

## 8. T6 材质与细节（22）

| 中文 | 英文 | 说明 / 搭配 |
| --- | --- | --- |
| 金属拉丝 | brushed metal | 产品、科技 |
| 磨砂金属 | matte metal | 克制、高级 |
| 高光烤漆 | glossy lacquer | 汽车、家电 |
| 玻璃 | glass | 通透、折射 |
| 磨砂玻璃 | frosted glass | 半透明、朦胧 |
| 陶瓷 | ceramic | 温润、手作 |
| 大理石 | marble | 纹理、厚重 |
| 混凝土 | concrete | 粗粝、工业 |
| 原木 | natural wood | 温暖、自然 |
| 皮革 | leather | 质感、缝线 |
| 织物 | fabric | 褶皱、柔软 |
| 丝绸 | silk | 光泽、垂坠 |
| 毛绒 | plush | 可爱、柔软 |
| 锈迹 | rust | 工业、时间感 |
| 水珠 | water droplets | 新鲜、清爽 |
| 烟雾 | smoke | 氛围、层次 |
| 灰尘 | dust particles | 光束可见、旧感 |
| 细腻纹理 | fine texture | 大特写必备 |
| 做旧 | weathered | 复古、年代感 |
| 半透明 | translucent | 玻璃、薄纱 |
| 反光 | reflective | 水面、镜面 |
| 哑光 | matte finish | 高级、不刺眼 |

## 9. T7 画质与技术（22）

| 中文 | 英文 | 说明 / 搭配 |
| --- | --- | --- |
| 8K | 8K resolution | 高细节，慎与「极简」同用 |
| 高分辨率 | high resolution | 通用 |
| 超精细细节 | ultra-detailed | 产品、概念图 |
| 锐利对焦 | sharp focus | 主体清晰 |
| HDR | high dynamic range | 光比大场景 |
| 电影级调色 | cinematic color grading | 统一色彩风格 |
| 色彩分级 | color grading | 冷暖、青橙 |
| 干净背景 | clean background | 电商、头像 |
| 无缝背景 | seamless backdrop | 影棚 |
| 影棚布光 | studio lighting | 产品标准 |
| 白底 | white background | 电商主图 |
| 产品级布光 | product lighting | 高光与阴影可控 |
| 真实反射 | realistic reflections | 金属/玻璃 |
| 物理正确材质 | physically based material | 3D/产品 |
| PBR 材质 | PBR material | 渲染术语 |
| 胶片颗粒 | film grain | 复古、电影感 |
| 低噪点 | low noise | 夜景、暗部 |
| 抗锯齿 | anti-aliasing | 线条、矢量 |
| 广色域 | wide color gamut | 印刷、屏幕 |
| 浅景深虚化 | bokeh | 背景光斑 |
| 微距细节 | macro detail | 纹理特写 |
| 边缘锐利 | crisp edges | 产品轮廓 |

## 10. T8 负面约束（24）

| 分组 | 中文 | 英文 | 说明 |
| --- | --- | --- | --- |
| 画质 | 低质量 | low quality | 默认必带 |
| 画质 | 模糊 | blurry | 默认必带 |
| 画质 | 噪点 | noisy | 夜景慎用「低噪点」冲突 |
| 画质 | 过曝 | overexposed | 强光场景 |
| 画质 | 畸变 | distorted | 广角/建筑 |
| 人体 | 多余肢体 | extra limbs | 人像必带 |
| 人体 | 缺失手指 | missing fingers | 人像必带 |
| 人体 | 面部崩坏 | deformed face | 近景/头像必带 |
| 人体 | 比例错误 | bad proportions | 全身/立绘 |
| 文字 | 文字水印 | text watermark | 默认必带 |
| 文字 | 签名 | signature | 插画/海报 |
| 文字 | 乱码文字 | gibberish text | 场景中含招牌时 |
| 文字 | logo | logo | 品牌合规 |
| 构图 | 主体裁切 | cropped subject | 主图/立绘 |
| 构图 | 杂乱背景 | cluttered background | 电商/头像 |
| 构图 | 重复元素 | duplicated elements | 群体/阵列 |
| 风格 | 风格混杂 | mixed styles | 与「混搭」需求冲突时需确认 |
| 风格 | 塑料感 | plastic look | 写实/产品 |
| 风格 | 过度磨皮 | over-smoothed skin | 人像 |
| 安全 | 真人可识别肖像 | identifiable real person | 红线，直接拦截 |
| 安全 | 商标复刻 | trademark reproduction | 红线，直接拦截 |
| 安全 | 暴力血腥 | gore and violence | 红线，直接拦截 |
| 安全 | 裸露 | nudity | 红线，直接拦截 |
| 安全 | 仇恨符号 | hate symbols | 红线，直接拦截 |

## 11. 禁用与替换清单

| 禁用类型 | 示例 | 替换写法 |
| --- | --- | --- |
| 在世艺术家姓名 | 「某某艺术家风格」 | 用流派/年代/媒介：「2010 年代电影感摄影」「厚涂油画质感」 |
| 工作室/公司风格 | 「某动画工作室风格」 | 用技法描述：「日式动画赛璐璐上色」「3D 卡通渲染」 |
| 商标与品牌 | 「某品牌 logo」「某可乐瓶」 | 用通用描述：「红色易拉罐」「极简商标位留空」 |
| 版权角色/IP | 「某动漫角色」 | 用特征描述：「戴草帽的少年」「机甲战士」 |
| 真人姓名/明星 | 「某明星的脸」 | 用人群特征：「30 岁亚洲男性，短发，商务休闲」 |
| 可识别真实场景门牌 | 具体地址、门牌号 | 用泛化场景描述 |

## 12. 阶段 1 验收对照

| 验收项 | 要求 | 本文件情况 |
| --- | --- | --- |
| 类别完整 | 8 类 | T1–T8 共 8 类 |
| 每类条目 | ≥20 条 | 24 / 22 / 22 / 24 / 28 / 22 / 22 / 24 |
| 双语可映射 | 每个词条有英文写法 | 100% 覆盖 |
| 冲突可识别 | 列出互斥组合 | 第 1 节规则 5 + 第 10 节「风格混杂」 |
| 安全边界 | 明确禁用与替换 | 第 10 节红线 5 条 + 第 11 节替换表 |
| 总量 | v0.1 ≥160 条 | 188 条 |

**阶段 3 扩写计划**：在 v0.1 基础上每类扩到 40–80 条，补别名、适用领域权重与越界降权规则；新增词必须过扩词基准确认不退化。
