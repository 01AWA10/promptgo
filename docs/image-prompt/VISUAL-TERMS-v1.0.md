# 视觉术语表 v1.0

> 阶段 3 交付物 · 2026-11-16 · 关联：[`../IMAGE-PROMPT-ITERATION-PLAN.md`](../IMAGE-PROMPT-ITERATION-PLAN.md)
> 上游：[`VISUAL-TERMS-v0.1.md`](VISUAL-TERMS-v0.1.md)（188 条）｜下游：[`IMAGE-PROMPT-SPEC-v1.0.md`](IMAGE-PROMPT-SPEC-v1.0.md)（8 段结构）、[`DOMAIN-STYLE-MAP-v0.1.md`](DOMAIN-STYLE-MAP-v0.1.md)（越界判定）
> 本版把 v0.1 的 8 类整理为**计划要求的 6 维度 + 主体补充**，每类扩到 40+ 条，**共 325 条**，并为每条补「别名 + 场景适配」，供 analyzer 直接建词典。

## 1. 相对 v0.1 的变更

| 变更 | v0.1 | v1.0 | 原因 |
| --- | --- | --- | --- |
| 分类口径 | T1–T8 平铺 | **6 维度**（风格/光线/镜头/构图/材质/画质与负面）+ T1 主体作补充 | 对齐计划「6 类视觉词表」，主体由槽位抽取，不靠词表匹配 |
| 条目量 | 188 | 325 | 目标 ≥300 |
| 字段 | 中文/英文/说明 | 中文/英文/**别名**/**场景适配** | 别名用于召回，场景用于抑制越界（见第 3 节） |
| 冲突处理 | 仅列举 | 独立冲突对表（第 12 节，12 组） | 可脚本化检测 |
| 负面词 | 混入说明列 | 按 6 组分类 + 强制等级（第 11 节） | 与规范 §8 的「必含 4 项 / 条件项」对齐 |

## 2. 维度与场景编码

**场景编码**（沿用 [`SCENARIO-MATRIX.md`](SCENARIO-MATRIX.md)）：`MK` 营销配图 · `EC` 电商主图 · `IL` 插画封面 · `AV` 头像人设 · `PS` 海报展板 · `CD` 概念分镜。

**维度对应**：

| 计划维度 | 本表章节 | 条数 |
| --- | --- | --- |
| 风格/流派 | §8 T5 风格与媒介 | 45 |
| 光线 | §7 T4 光线与氛围 | 40 |
| 镜头与焦段 | §6 T3 景别与镜头 | 40 |
| 构图与视角 | §5 T2 构图与视角 | 40 |
| 材质与细节 | §9 T6 材质与细节 | 40 |
| 画质与负面 | §10 T7 画质与技术 / §11 T8 负面约束 | 40 + 40 |
| （补充）主体与动作 | §4 T1 主体与动作 | 40 |
| — | 合计 | **325** |

## 3. 命中、归一与权重

1. **最长匹配优先**：「侧逆光」先于「逆光」，「超广角 16mm」先于「广角」，避免短词抢命中。
2. **别名归一**：别名命中后统一输出主词，`aliases` 不参与渲染；同一别名不得跨维度复用（跨类复用视为冲突，见第 12 节）。
3. **场景权重**：`场景` 列即该词的适用权重来源——
   - 词条场景 **包含** 当前场景 → 权重 **1.0**；
   - 词条场景 **不包含** 但相邻（同属「写实/插画」大类）→ **0.9**（保留，低优先）；
   - 词条场景 **不包含** 且跨大类（如 EC 场景命中「荷兰角」）→ **0.7**，且不主动推荐，仅在用户显式点名时使用。
4. **显式提权**：用户原话或引号内直接点名该词 → **+0.1**（封顶 1.1）。
5. **每维上限**：同一维度最多输出 3 词（风格维度 1 主 + 1 辅），超出按权重截断。
6. **去重**：主词与输出文本重复时只保留一次；负面词与正文词不得同形（同形即删负面）。

## 4. T1 主体与动作（40）

主体主要由槽位抽取得到，本表用于**兜底识别与默认补全**（用户只说「一张图」时按场景取默认主体）。

| 中文 | 英文 | 别名 | 场景 |
| --- | --- | --- | --- |
| 单人半身像 | half-body portrait | 半身人像、半身照 | AV PS |
| 全身人像 | full-body portrait | 全身照、立绘 | AV IL |
| 双人 | two people | 两人、对谈 | MK IL |
| 群体 | group of people | 一群人、人群 | MK CD |
| 背影 | seen from behind | 背对镜头 | IL CD |
| 剪影 | silhouette | 暗部剪影 | PS CD |
| 儿童 | child | 小孩、孩童 | MK IL |
| 老人 | elderly person | 长者 | MK IL |
| 宠物 | pet | 猫狗、萌宠 | MK AV |
| 动物 | wild animal | 野生动物 | IL CD |
| 婴儿 | baby | 新生儿 | AV |
| 学生 | student | 校园人物 | MK IL |
| 厨师 | chef | 后厨人物 | MK |
| 团队群像 | team group photo | 团队合影 | MK |
| 双人合影 | couple portrait | 合影 | AV MK |
| 面部特写 | face close-up | 脸部特写 | AV |
| 手部特写 | hand detail | 手持、握持 | EC |
| 行走 | walking | 步行、走动 | MK CD |
| 奔跑 | running | 跑步 | MK PS |
| 坐姿 | seated | 端坐、坐着 | MK IL |
| 俯身 | leaning forward | 前倾 | MK EC |
| 伸手 | reaching out | 伸手取物 | MK EC |
| 回头 | looking back over shoulder | 回眸 | AV IL |
| 交谈 | talking with each other | 对话、交流 | MK IL |
| 工作状态 | working | 工位、办公中 | MK PS |
| 阅读 | reading | 看书 | MK IL |
| 骑行 | cycling | 骑车 | CD MK |
| 悬浮 | floating | 漂浮 | EC PS |
| 产品静物 | product still life | 静物、单品 | EC |
| 食物特写 | food close-up | 菜品特写 | MK EC |
| 植物特写 | botanical close-up | 绿植、花草 | MK EC |
| 建筑外观 | building exterior | 外立面 | PS CD |
| 室内空间 | interior space | 内景 | CD PS |
| 风景 | landscape | 风光、自然景观 | CD MK |
| 载具 | vehicle | 车辆、交通工具 | MK CD |
| 机器人 | robot | 机械体 | CD AV |
| 图标组 | icon set | 图标、ICON | AV PS |
| 界面稿 | UI mockup | 界面、UI | AV PS |
| 抽象几何 | abstract geometry | 几何体 | PS CD |
| 环境空镜 | empty scene | 无人场景、空镜 | PS CD |

## 5. T2 构图与视角（40）

| 中文 | 英文 | 别名 | 场景 |
| --- | --- | --- | --- |
| 三分法 | rule of thirds | 九宫格、三分构图 | MK IL CD PS |
| 中心构图 | centered composition | 居中构图、中央构图 | EC AV PS |
| 对称构图 | symmetrical composition | 镜像构图 | PS CD |
| 对角线构图 | diagonal composition | 斜线构图 | MK CD |
| 引导线 | leading lines | 汇聚线 | CD PS |
| 框架构图 | framing | 画中画、门窗取景 | CD IL |
| 前景层次 | foreground layering | 前景遮挡 | MK CD |
| 负空间 | negative space | 留白区、空白区 | PS AV |
| 黄金分割 | golden ratio | 黄金比例 | PS AV |
| 重复韵律 | repeating pattern | 阵列、韵律 | PS CD |
| 仰视 | low angle | 低角度、仰拍 | MK CD |
| 俯视 | high angle | 高角度、俯拍 | MK CD |
| 平视 | eye level | 视平线、平拍 | 全场景 |
| 鸟瞰 | bird's-eye view | 顶拍、正上方 | PS CD |
| 广角透视 | wide-angle perspective | 广角拉伸 | CD PS |
| 长焦压缩 | telephoto compression | 背景压缩 | AV MK |
| 浅景深 | shallow depth of field | 背景虚化、景深浅 | AV EC MK |
| 深景深 | deep focus | 全景清晰 | CD PS |
| 极简构图 | minimalist composition | 少元素、克制构图 | PS AV EC |
| 满版构图 | full-bleed composition | 满幅、无边框 | PS CD |
| 中心留空 | centered empty space | 中央留白、中心留位 | PS |
| 版式留白 | layout whitespace | 排版留白 | PS MK |
| 上方留白 | top whitespace | 顶部留白、上方留位 | PS IL |
| 右侧留白 | right-side whitespace | 右侧留位、右留白 | MK PS |
| 左侧留白 | left-side whitespace | 左侧留位、左留白 | MK PS |
| 下方留白 | bottom whitespace | 底部留白 | PS MK |
| S 形构图 | S-curve composition | 曲线引导 | CD IL |
| 三角形构图 | triangular composition | 三角稳定 | PS CD |
| 放射构图 | radial composition | 中心放射 | PS CD |
| 水平线构图 | horizontal-line composition | 横平构图 | CD |
| 垂直线构图 | vertical-line composition | 竖直构图 | PS CD |
| 曲线构图 | curved-line composition | 弧线构图 | IL CD |
| 单点透视 | one-point perspective | 一点透视 | CD PS |
| 等距视角 | isometric viewpoint | 等轴视角 | IL PS |
| 微距视角 | macro viewpoint | 超近距离 | EC |
| 第一人称视角 | first-person view | POV 视角 | CD |
| 俯角 45 度 | 45-degree high angle | 四十五度俯拍 | EC MK |
| 贴地视角 | ground-level view | 地面视角 | CD MK |
| 平铺构图 | flat lay | 俯拍平铺、摆拍 | EC MK |
| 阶梯层次 | stepped layers | 层层递进 | CD PS |

## 6. T3 景别与镜头（40）

| 中文 | 英文 | 别名 | 场景 |
| --- | --- | --- | --- |
| 远景 | long shot | 大远景、wide shot | CD MK |
| 全景 | full shot | 全景别 | MK CD |
| 中景 | medium shot | 中景别 | MK CD PS |
| 近景 | close shot | 近景别 | AV EC |
| 特写 | close-up | 特写镜头 | EC AV |
| 大特写 | extreme close-up | 微特写 | EC AV |
| 半身景 | half shot | 半身像景别 | AV |
| 全身景 | full-body shot | 全身构图 | IL AV |
| 环境肖像 | environmental portrait | 场景人像 | MK |
| 过肩镜头 | over-the-shoulder shot | 越肩视角 | CD |
| 荷兰角 | Dutch angle | 倾斜构图、歪镜头 | CD |
| 鱼眼镜头 | fisheye lens | 球形镜头 | CD |
| 标准镜头 | standard lens | 常规镜头 | 全场景 |
| 35mm 镜头 | 35mm lens | 三五镜头 | MK CD |
| 50mm 镜头 | 50mm lens | 五零镜头 | AV MK |
| 85mm 镜头 | 85mm lens | 人像镜头 | AV |
| 135mm 镜头 | 135mm lens | 中长焦 | AV |
| 200mm 长焦 | 200mm telephoto | 长焦镜头 | CD |
| 24mm 广角 | 24mm wide | 二四广角 | CD PS |
| 16mm 超广角 | 16mm ultra-wide | 超广角镜头 | CD |
| 移轴镜头 | tilt-shift lens | 移轴 | CD PS |
| 微距镜头 | macro lens | 微距 | EC |
| 变形宽银幕 | anamorphic widescreen | 宽银幕镜头 | CD |
| 定焦镜头 | prime lens | 定焦 | AV EC |
| 变焦镜头 | zoom lens | 变焦 | MK |
| 中画幅 | medium format | 中画幅相机 | EC AV |
| 大光圈 f/1.4 | wide aperture f/1.4 | 大光圈 | AV EC |
| 小光圈 f/11 | small aperture f/11 | 小光圈 | CD EC |
| 高速快门 1/1000s | high-speed shutter | 凝固快门 | MK CD |
| 慢门 1/15s | slow shutter | 慢速快门、拖影 | CD |
| 长曝光 | long exposure | 长曝 | CD |
| 手持纪实 | handheld documentary | 手持跟拍 | MK CD |
| 航拍 | aerial photography | 无人机视角 | CD PS |
| 水下摄影 | underwater photography | 水中拍摄 | CD |
| 全景接片 | panoramic stitch | 接片、宽幅拼接 | CD PS |
| 延时摄影 | time-lapse | 延时 | CD |
| 监控视角 | security-camera view | 摄像头视角 | CD |
| 手机视角 | phone-camera look | 手机拍摄 | MK |
| 复古镜头 | vintage lens | 老镜头、柔光老镜 | CD AV |
| 四分之三侧脸 | three-quarter face | 侧脸 45 度 | AV |

## 7. T4 光线与氛围（40）

| 中文 | 英文 | 别名 | 场景 |
| --- | --- | --- | --- |
| 自然光 | natural light | 环境光、天光 | MK CD IL |
| 黄金时刻 | golden hour | 日落光、日出光 | MK CD |
| 蓝调时刻 | blue hour | 暮蓝、日落后冷光 | CD PS |
| 正午硬光 | harsh midday light | 顶头光、正午光 | MK CD |
| 顺光 | front lighting | 正面光 | EC AV |
| 侧光 | side lighting | 侧向光 | EC CD |
| 逆光 | backlighting | 背光 | IL CD |
| 侧逆光 | side-back lighting | 侧逆光位、发丝光 | MK AV |
| 顶光 | top lighting | 上方光 | CD |
| 底光 | under lighting | 下方光 | CD |
| 伦勃朗光 | Rembrandt lighting | 三角光 | AV |
| 蝴蝶光 | butterfly lighting | 美人光 | AV EC |
| 柔光 | soft light | 柔和光、软光 | EC AV MK |
| 硬光 | hard light | 强光、硬边光 | MK CD |
| 窗光 | window light | 侧窗光、自然窗光 | MK IL |
| 霓虹光 | neon lighting | 霓虹灯、彩色管光 | CD |
| 烛光 | candlelight | 烛火 | IL CD |
| 体积光 | volumetric light | 丁达尔光、光束 | CD PS |
| 轮廓光 | rim light | 边缘光、分离光 | EC AV |
| 高调 | high-key | 高亮调、亮调 | EC AV |
| 低调 | low-key | 暗调、低调光 | CD IL |
| 明暗对比 | chiaroscuro | 强明暗、光影对比 | CD PS |
| 雾气 | atmospheric fog | 薄雾、晨雾 | CD IL |
| 颗粒氛围 | grainy atmosphere | 颗粒感 | CD IL |
| 三点布光 | three-point lighting | 标准布光 | EC AV |
| 美人碟光 | beauty dish | 雷达罩 | AV |
| 柔光箱 | softbox lighting | 柔光罩 | EC AV |
| 反光板补光 | bounce fill | 补光板、反光补光 | EC |
| 阴天散射光 | overcast diffused light | 阴天光、散射光 | MK CD |
| 路灯照明 | street lamp glow | 路灯、街灯 | CD |
| 车灯照明 | car headlight glow | 车灯、头灯 | CD |
| 屏幕光 | screen glow | 屏幕反光、显示器光 | CD MK |
| 火光 | firelight | 火焰光、炉火光 | IL CD |
| 舞台追光 | stage spotlight | 追光、聚光灯 | PS CD |
| 直闪 | direct flash | 闪光灯直打、硬闪 | MK CD |
| 漏光光斑 | light leak | 漏光、胶片漏光 | IL PS |
| 冷调月光 | cool moonlight | 月光、冷月 | IL CD |
| 暖调夕照 | warm sunset glow | 夕阳光、暖黄光 | MK CD |
| 双色温对比 | mixed color temperature | 冷暖对撞、双色温 | CD PS |
| 无影平光 | shadowless flat light | 平光、无阴影光 | EC AV |

## 8. T5 风格与媒介（45）

| 中文 | 英文 | 别名 | 场景 |
| --- | --- | --- | --- |
| 写实摄影 | photorealistic photography | 真实照片、超写实 | 全场景 |
| 纪实摄影 | documentary photography | 纪实、抓拍风 | MK CD |
| 商业产品摄影 | commercial product photography | 产品摄影、商业棚拍 | EC MK |
| 时尚大片 | fashion editorial | 时尚杂志、editorial | MK AV |
| 电影感 | cinematic | 电影感调色、宽银幕感 | CD PS MK |
| 概念设定 | concept art | 概念图、概念设计、设定图 | CD MK PS |
| 胶片摄影 | film photography | 胶片风、菲林 | IL CD |
| 黑白摄影 | black-and-white photography | 黑白、单色照片 | PS CD |
| 水彩 | watercolor | 水彩晕染 | IL PS |
| 油画 | oil painting | 厚涂油画 | IL PS |
| 丙烯 | acrylic painting | 丙烯画 | IL |
| 素描 | pencil sketch | 铅笔稿、素描稿 | IL |
| 版画 | printmaking | 木刻版画 | IL PS |
| 水墨 | ink wash painting | 国画水墨、写意 | IL PS |
| 扁平插画 | flat illustration | 扁平风、矢量平涂 | AV IL PS |
| 矢量插画 | vector illustration | 矢量图 | AV PS |
| 2.5D 插画 | 2.5D illustration | 伪立体插画 | IL AV |
| 等距插画 | isometric illustration | 等轴插画 | IL PS |
| 3D 渲染 | 3D render | 三维渲染、C4D 风 | EC AV CD |
| 黏土动画 | claymation | 黏土风、橡皮泥 | AV IL |
| 像素艺术 | pixel art | 像素风、8bit | IL AV |
| 赛博朋克 | cyberpunk | 赛博、霓虹未来 | CD |
| 蒸汽朋克 | steampunk | 蒸汽机械、黄铜齿轮 | CD IL |
| 极简主义 | minimalism | 极简风、性冷淡风 | PS EC AV |
| 构成主义 | constructivism | 俄国构成、几何海报 | PS |
| 装饰艺术 | Art Deco | 装饰风、金属线条 | PS CD |
| 国潮插画 | Chinese-chic illustration | 新国潮、国风插画 | MK PS IL |
| 日式动画赛璐璐 | anime cel shading | 赛璐璐、日式动画 | AV IL |
| 低多边形 | low poly | 低模、几何切面 | AV CD |
| 波普艺术 | pop art | 波普、安迪沃霍尔式网点 | PS IL |
| 复古海报 | retro poster | 老海报、复古印刷 | PS MK |
| 蓝晒 | cyanotype | 蓝晒法、普鲁士蓝 | IL PS |
| 双重曝光 | double exposure | 叠影 | IL PS |
| 拼贴 | collage | 拼贴画、剪贴 | PS IL |
| 纸雕 | paper cut-out | 剪纸、纸片层叠 | IL PS |
| 彩铅 | colored pencil | 彩色铅笔 | IL |
| 美漫线条 | American comic inking | 美漫风、硬线条 | IL |
| 法式漫画 | bande dessinée | 欧漫、法漫 | IL |
| 线稿上色 | line art with color | 线稿、描线上色 | IL AV |
| 霓虹插画 | neon illustration | 霓虹线稿、荧光线条 | PS CD |
| 玻璃拟态 | glassmorphism | 毛玻璃界面风 | PS AV |
| 柔焦朦胧 | soft-focus haze | 柔焦、朦胧感 | AV IL |
| 微缩模型 | miniature diorama | 微缩场景、模型感 | CD IL |
| 产品爆炸图 | exploded product view | 结构爆炸图 | EC CD |
| 建筑效果图 | architectural rendering | 建筑渲染、效果图 | PS CD |

## 9. T6 材质与细节（40）

| 中文 | 英文 | 别名 | 场景 |
| --- | --- | --- | --- |
| 金属拉丝 | brushed metal | 拉丝金属 | EC CD |
| 磨砂金属 | matte metal | 喷砂金属 | EC AV |
| 高光烤漆 | glossy lacquer | 亮面烤漆 | EC MK |
| 玻璃 | glass | 透明玻璃 | EC PS |
| 磨砂玻璃 | frosted glass | 毛玻璃 | EC PS |
| 陶瓷 | ceramic | 瓷质 | EC MK |
| 大理石 | marble | 石材纹理 | PS EC |
| 混凝土 | concrete | 水泥 | CD PS |
| 原木 | natural wood | 实木、木纹 | MK CD |
| 皮革 | leather | 真皮、皮纹 | EC AV |
| 织物 | fabric | 布料、织纹 | EC MK |
| 丝绸 | silk | 缎面、真丝 | EC AV |
| 毛绒 | plush | 绒毛、长毛绒 | AV IL |
| 锈迹 | rust | 铁锈、锈蚀 | CD |
| 水珠 | water droplets | 水滴、凝结水 | EC MK |
| 烟雾 | smoke | 烟气 | CD PS |
| 灰尘 | dust particles | 浮尘 | CD |
| 细腻纹理 | fine texture | 细纹理、微纹理 | EC CD |
| 做旧 | weathered | 旧化、磨损 | CD IL |
| 半透明 | translucent | 透光、半透 | EC PS |
| 反光 | reflective | 镜面反光 | EC CD |
| 哑光 | matte finish | 雾面、不反光 | EC AV |
| 黄铜 | brass | 铜金色 | CD IL |
| 不锈钢 | stainless steel | 钢质 | EC |
| 铝合金 | aluminum alloy | 铝材 | EC |
| 碳纤维 | carbon fiber | 碳纤纹理 | EC CD |
| 亚克力 | acrylic | 有机玻璃 | EC PS |
| 硅胶 | silicone | 软胶 | EC |
| 橡胶 | rubber | 橡胶质感 | EC CD |
| 漆皮 | patent leather | 亮面皮 | EC AV |
| 天鹅绒 | velvet | 丝绒 | AV PS |
| 牛仔布 | denim | 丹宁 | MK AV |
| 针织 | knitwear | 毛线、针织纹理 | MK EC |
| 纸张 | paper | 纸质感 | PS IL |
| 牛皮纸 | kraft paper | 牛皮纸质 | PS MK |
| 石膏 | plaster | 石膏白模 | CD PS |
| 冰晶 | ice crystal | 冰面、霜 | EC CD |
| 金属箔 | metallic foil | 烫金、金箔 | PS EC |
| 玻璃纤维 | fiberglass | 玻纤 | CD EC |
| 石材 | stone | 天然石 | CD PS |

## 10. T7 画质与技术（40）

| 中文 | 英文 | 别名 | 场景 |
| --- | --- | --- | --- |
| 8K | 8K resolution | 8K 分辨率、超高清 | EC CD |
| 高分辨率 | high resolution | 高清、HR | 全场景 |
| 超精细细节 | ultra-detailed | 细节拉满 | EC CD |
| 锐利对焦 | sharp focus | 焦点锐利 | EC AV |
| HDR | high dynamic range | 高动态范围 | CD PS |
| 电影级调色 | cinematic color grading | 电影调色 | CD MK |
| 色彩分级 | color grading | 调色、色阶统一 | CD PS |
| 干净背景 | clean background | 背景干净 | EC AV |
| 无缝背景 | seamless backdrop | 无缝纸、无接缝背景 | EC |
| 影棚布光 | studio lighting | 影棚光 | EC AV |
| 白底 | white background | 纯白底、白背景 | EC |
| 产品级布光 | product lighting | 产品光 | EC |
| 真实反射 | realistic reflections | 物理反射 | EC CD |
| PBR 材质 | PBR material | 物理渲染材质 | EC CD |
| 胶片颗粒 | film grain | 颗粒感 | IL CD |
| 低噪点 | low noise | 无噪点、降噪 | CD EC |
| 抗锯齿 | anti-aliasing | 边缘平滑 | AV PS |
| 广色域 | wide color gamut | 色域广 | PS EC |
| 背景虚化 | bokeh | 光斑、焦外 | AV EC |
| 微距细节 | macro detail | 近摄细节 | EC |
| 边缘锐利 | crisp edges | 轮廓清晰 | EC PS |
| 16bit 色深 | 16-bit color depth | 高位深 | PS CD |
| 高对比 | high contrast | 强对比 | CD PS |
| 低饱和 | low saturation | 低彩度、灰调 | PS AV |
| 高饱和 | high saturation | 高彩度、浓色 | MK IL |
| 青橙色调 | teal and orange | 青橙调色 | CD MK |
| 莫兰迪色 | Morandi palette | 高级灰、低饱和配色 | PS AV |
| 单色调 | monochrome | 同色系 | PS CD |
| 双色调 | duotone | 双色版 | PS IL |
| 高光细节 | highlight detail | 高光不溢出 | EC CD |
| 暗部通透 | clean shadows | 暗部细节 | CD |
| 中性灰背景 | neutral gray background | 灰底 | EC AV |
| 印刷网点 | halftone dots | 网点 | PS IL |
| 色差校正 | chromatic correction | 紫边校正 | CD |
| 轻微柔化 | subtle softening | 柔化处理 | AV IL |
| 清晰层次 | clear tonal layers | 层次分明 | CD PS |
| 无损锐化 | unsharp mask | USM 锐化 | EC |
| 抖动降噪 | dithering | 抖动处理 | PS |
| 伽马校正 | gamma correction | 伽马 | PS EC |
| 无压缩伪影 | no compression artifacts | 无压缩块 | 全场景 |

## 11. T8 负面约束（40）

**强制等级**：`必带` = 规范 §8 的通用 4 项，任何场景都注入；`条件` = 按主体/场景注入；`场景` = 由场景矩阵追加；`红线` = 不写进负面词，走前置拦截（见规范 §8）。

| 组 | 中文 | 英文 | 别名 | 等级 | 场景 |
| --- | --- | --- | --- | --- | --- |
| 画质 | 低质量 | low quality | 糊图、劣质 | 必带 | 全场景 |
| 画质 | 模糊 | blurry | 发虚、不清楚 | 必带 | 全场景 |
| 画质 | 比例畸变 | bad proportions | 变形、走形 | 必带 | 全场景 |
| 画质 | 文字水印 | text watermark | 水印字、角标 | 必带 | 全场景 |
| 画质 | 噪点 | noisy | 颗粒噪点 | 条件 | CD EC |
| 画质 | 过曝 | overexposed | 死白、爆光 | 场景 | EC MK |
| 画质 | 欠曝 | underexposed | 死黑 | 条件 | CD |
| 画质 | 畸变 | distorted | 桶形畸变、广角变形 | 条件 | CD PS |
| 人体 | 多余肢体 | extra limbs | 多余手臂、多腿 | 条件 | AV IL |
| 人体 | 多余手指 | extra fingers | 六指 | 条件 | AV |
| 人体 | 缺失手指 | missing fingers | 断指、手指残缺 | 条件 | AV |
| 人体 | 面部崩坏 | deformed face | 脸崩、五官错位 | 条件 | AV IL |
| 人体 | 扭曲手部 | bad hands | 手部崩坏 | 条件 | AV EC |
| 人体 | 皮肤比例错误 | wrong skin proportions | 身材比例失调 | 条件 | AV |
| 文字 | 签名 | signature | 作者签名 | 场景 | IL PS |
| 文字 | 乱码文字 | gibberish text | 假字、错字招牌 | 场景 | CD PS |
| 文字 | logo | logo | 品牌标识 | 场景 | EC MK |
| 文字 | 说明文字 | caption text | 角标文案 | 场景 | PS |
| 文字 | 水印边框 | watermark border | 边框水印 | 场景 | PS IL |
| 构图 | 主体裁切 | cropped subject | 主体出框 | 场景 | EC AV |
| 构图 | 边缘裁切 | edge cutoff | 裁边、切边 | 场景 | PS |
| 构图 | 杂乱背景 | cluttered background | 背景杂乱、元素太多 | 条件 | EC AV MK |
| 构图 | 重复元素 | duplicated elements | 复制人、重影 | 条件 | MK CD |
| 构图 | 主体压字 | text over subject | 文字压主体 | 场景 | PS |
| 构图 | 构图歪斜 | tilted horizon | 地平线倾斜 | 条件 | CD |
| 构图 | 空白过多 | excessive empty space | 太空、内容不足 | 条件 | PS EC |
| 风格 | 风格混杂 | mixed styles | 风格打架 | 条件 | 全场景 |
| 风格 | 塑料感 | plastic look | 塑料质感 | 条件 | EC CD |
| 风格 | 塑料皮肤 | plastic skin | 假脸、油光脸 | 条件 | AV |
| 风格 | 过度磨皮 | over-smoothed skin | 磨皮过度 | 条件 | AV |
| 风格 | 强行 HDR | overprocessed HDR | 假 HDR | 条件 | CD PS |
| 风格 | 低多边形伪影 | low-poly artifacts | 块面破碎 | 条件 | EC AV |
| 其他 | 现代元素 | modern elements | 穿帮现代物件 | 场景 | CD IL |
| 其他 | 恐怖元素 | horror elements | 血腥惊悚 | 场景 | IL CD |
| 其他 | 可识别车牌 | readable license plate | 车牌清楚 | 场景 | MK |
| 其他 | 拼贴接缝 | collage seams | 拼接痕迹 | 条件 | PS |
| 其他 | 过时滤镜 | dated filter | 土味滤镜 | 条件 | MK PS |
| 安全 | 真人可识别肖像 | identifiable real person | 真人正脸 | 红线 | 全场景 |
| 安全 | 商标复刻 | trademark reproduction | 复刻商标 | 红线 | 全场景 |
| 安全 | 暴力血腥 | gore and violence | 血腥画面 | 红线 | 全场景 |

> 安全组仅 3 条入表用于**检测与改写提示**（命中即触发改写或拦截），不注入负面词——理由见规范 §8：否定式在扩散模型中可能被反向激活。暴力/裸露/仇恨符号的完整红线清单见 [`INTENT-BOUNDARY-v0.1.md`](INTENT-BOUNDARY-v0.1.md)。

## 12. 冲突对清单（12 组，供脚本检测）

| # | 组合 | 冲突类型 | 处置 |
| --- | --- | --- | --- |
| 1 | 写实摄影 × 卡通渲染/像素艺术 | 媒介互斥 | 保留用户显式点名者，另一词降 0.7 并提示 |
| 2 | 极简主义 × 满版构图/繁复装饰 | 密度互斥 | 保留极简，删除满版 |
| 3 | 高调 × 低调 | 影调互斥 | 要求用户二选一（追问一次） |
| 4 | 柔光 × 硬光 | 光质互斥 | 按场景取：EC/AV→柔光，MK/CD→硬光 |
| 5 | 浅景深 × 深景深 | 景深互斥 | 取用户最后提及者 |
| 6 | 低饱和 × 高饱和 | 色彩互斥 | 冲突则都删，交默认值 |
| 7 | 无影平光 × 强明暗对比 | 光比互斥 | 保留明暗对比（信息量更大） |
| 8 | 黑白摄影 × 青橙色调 | 色彩互斥 | 删色调词 |
| 9 | 中心构图 × 三分法 | 法则重叠 | 保留先命中者 |
| 10 | 鸟瞰 × 平视 | 机位互斥 | 保留先命中者 |
| 11 | 胶片颗粒 × 低噪点 | 画质互斥 | 有「年代感」需求时保留颗粒，删低噪点 |
| 12 | 赛博朋克 × 水墨/国潮 | 风格跨类 | 显式标注为「混搭」并在输出中加「风格融合过渡」 |

## 13. 验收对照

| 验收项 | 要求 | 本文件情况 |
| --- | --- | --- |
| 词条总量 | ≥300 | 325 |
| 单类条目 | 40–80 | 40 / 40 / 40 / 40 / 44 / 40 / 40 / 40 |
| 双语 | 每条含英文 | 325/325 |
| 别名 | 每条含中文别名 | 325/325（同形词以「同形」处理除外） |
| 场景权重 | 每条标注适用场景 | 325/325，权重规则见第 3 节 |
| 冲突可检测 | 列出互斥组合 | 12 组 |
| 安全 | 无在世艺术家/品牌/IP | 全部为流派、技法、材质级描述 |

**代码侧现状（2026-11-16，已同步）**：`server/engine/visual.py` 已落地**全量 325 条**
（主体 40 / 构图 40 / 镜头 40 / 光线 40 / 风格 44 / 材质 40 / 画质 40 / 负面 40），
字段与本表一致（`中文|english|别名|场景`），一致性由 `tests/test_image.py::LexiconTestCase` 守护。

额外新增**口语别名层** `_ALIAS_EXTRA`（约 40 条词各挂 2–4 个口语说法，如「黄昏」→ 黄金时刻、
「压扁」→ 长焦压缩、「性冷淡」→ 极简主义）。别名只参与召回，渲染仍输出主词。

召回基准实测：风格 / 镜头 / 光线三维度**均 100%（行级）**，术语级 72%，
明细与口径见 [`RECALL-REPORT-v0.1.md`](RECALL-REPORT-v0.1.md)。
