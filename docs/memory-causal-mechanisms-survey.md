# 人間の記憶を成立させている因果機構：S2 の文献調査と理論の整理（v0.1）

> 作成：2026-10-14（Claude）。ChatGPT の承認（S2 の文献調査と理論の整理、docs のみ）に従う。前提は `docs/s1-s2-research-direction.md`（#95）
> **問い**（ChatGPT）：**人間の記憶は、どのような因果機構によって成立しており、そのうち何を AnIma-ll の内部力学として保存する必要があるのか**
>
> Status：**文献調査と理論の整理。設計の決定でも、事前登録でもない。** 次のことはしない
> - 現行 Core の変更。Unit 数・可塑性・DB の方式の決定。B5 への移行
> - 実験・seed の実行。保存済みの raw への新しい指標の当てはめ
> - Unit の構造（Wilson–Cowan 型・イベント型・海馬型の回路など）を先に選び、それに合わせて記憶を定義すること
>
> 3 Unit の研究模型は比較の基準として保持する。Q3 は保留のまま
>
> 前提として読む文書：`docs/s1-s2-research-direction.md`（#95）、`docs/core-structural-reassessment.md`（#94。以下「再評価」）、`docs/internal-representation-principles.md`（以下「原則」）、`docs/arbitrariness-audit.md`（以下「台帳」）、`docs/spontaneous-temporal-pattern-identifiability.md`（#89。以下「識別のメモ」）

---

## 0. 読み方

### 0.1 三つの区別（ChatGPT の指定）

各領域で、次の三つを分けて書く。

| 区別 | 何を書くか |
|---|---|
| **生物学的事実** | 脳で何が観測され、どの介入で因果関係が支持されたか |
| **計算論的な説明** | その機構がどのような働きを実現すると考えられているか |
| **AnIma-ll への必要性** | 同じ働きを作るのに、その生物学的機構そのものが必要か、別の構造でも実現しうるか |

### 0.2 証拠の札

| 札 | 意味 |
|---|---|
| 〔H-介入〕 | ヒトでの因果的な操作（睡眠中の刺激など） |
| 〔H-損傷〕 | ヒトの脳損傷・疾患の研究（自然に生じた損傷なので、範囲が揃わない） |
| 〔H-観察〕 | ヒトの脳画像・頭蓋内記録・行動の観察 |
| 〔A-介入〕 | 動物への介入（損傷・薬理・遺伝子操作・光遺伝学など） |
| 〔A-観察〕 | 動物の神経活動の記録 |
| 〔A-生理〕 | 動物の組織・スライスでの生理（行動との結びつきは直接は見ていない） |
| 〔理論〕 | 理論・計算模型 |
| 〔総説〕 | 総説（一次研究ではない） |

**一般化の注意**：「ある回路が、マウスのある課題に必要だった」〔A-介入〕は、その種・その課題・その操作の範囲の結果である。「あらゆる人工の記憶システムに必要」とは一般化しない。ヒトの損傷研究は、損傷の範囲が人ごとに違い、代償も起きるので、単一の部位の必要性を示すには限界がある。

### 0.3 AnIma-ll の候補の札

各領域の最後の「AnIma-ll で保存すべき因果関係の候補」には、次の札を付ける。**どれも採用の決定ではない。**

| 札 | 意味 |
|---|---|
| **【働き：強い候補】** | 最終目標「人間と同等以上の記憶機能」（#95 §0.1）から、働きとして求められる根拠が強い。ただし、どう実現するかは決めない |
| **【働き：候補】** | 人間の記憶の性質として実在するが、AnIma-ll の目標に必須かの根拠はまだ弱い |
| **【未決】** | 必要かどうか判断する材料が足りない |
| **〔機構：代替あり〕** | 同じ働きを、生物と違う構造で実現した例がある。その生物学的機構そのものは必須ではないと考えられる（ただし代替が AnIma-ll の原則を満たすかは別に監査する） |
| **〔機構：未決〕** | 機構の必要性は判断できない |

候補の番号には、領域ごとの接頭辞を付ける：符号化 Enc、保持・固定化 Con、想起・再構成 Rec、連想・一般化 Gen、干渉・忘却 Fgt、記憶の利用 Use。§8 の比較の軸は MF1〜MF9 とする。再評価の E1〜E8・S1〜S6、原則の R1〜R6、保留中の Q3 などと番号が衝突しないようにするためである。

### 0.4 記憶の現象と機構を分ける（ChatGPT の必須条件 2）

この文書では、次の語を別のものとして使う。互いに同一視しない。

| 語 | 意味（この文書での使い方） |
|---|---|
| **保持** | 経験による変化が、内部のどこかに残っていること |
| **再活性化** | 経験したときの神経活動の一部が、後で再び現れること（観測される現象） |
| **リプレイ** | 再活性化のうち、経験したときの活動の**順序**が、多くは時間を縮めた形で再び現れるもの |
| **想起** | 手がかりから、保持された変化を使って活動が再び形づくられ、それが後の処理に使われること |
| **行動の変化** | 後の行動が、経験に依存して変わること |

例えば、変化が保持されていても自然には想起できない場合がある（§3 の Ryan et al. 2015）。リプレイが起きたことは、想起が起きたことを意味しない。思い出したという自覚がなくても、行動は変わりうる（§6 の習慣・技能）。識別のメモの L1〜L3 と同じ立場で、現象の観測と、それを生んだ機構の同定を分ける（再評価 E1）。

### 0.5 文献の選び方と限界

- 各領域で、古典となった一次研究、因果の介入を含む一次研究、ヒトの研究、理論、総説を組み合わせた。網羅的な系統的レビューではない。選択には書き手（Claude）の知識の偏りが入る
- 引用した文献の DOI は、2026-10-14 に Crossref の登録情報（題名・第一著者・年・誌名）と照合した。DOI のない文献は URL を付けた
- 「何を示したか」の要約は、各論文の主な結果に限った。細かい数値や条件は原典で確認すること

---

## 1. 符号化：異なる経験や時間の順序が、どう区別されて書き込まれるか

### 1.1 生物学的知見

- **海馬が新しい出来事の記憶の形成に必要**：両側の内側側頭葉を切除した患者 H.M. は、新しい出来事を覚えられなくなった。一方、手術以前の古い記憶や技能の学習は比較的保たれた〔H-損傷〕[Scoville1957]。記憶には複数の系がある、という見方の出発点になった〔総説〕[Squire2004][Tulving2002]
- **シナプスの長期増強（LTP）**：入力を強く刺激すると、その経路の伝わりやすさが何時間も強くなる〔A-生理〕[Bliss1973]。NMDA 受容体を阻害すると、LTP と空間学習の両方が損なわれた〔A-介入〕[Morris1986]。ただし、別の迷路で前もって訓練したラットは、阻害の下でも新しい場所を学べた。阻害が損なったのは、学習の一部の成分だった〔A-介入〕[Bannerman1995]
- **発火の時刻の順で強まる・弱まる可塑性（STDP）**：送り手が受け手の直前に発火すると強まり、逆だと弱まる。窓は数十ミリ秒〔A-生理〕[Markram1997][Bi1998]
- **行動の時間尺度の可塑性（BTSP）**：海馬 CA1 のニューロンで、一度の「プラトー電位」が、その前後**数秒**に活動した入力を強め、場所に応じた発火（場所細胞）を**一回の試行で**作った。生きたマウスで、電流の注入によりプラトーを人工的に起こして確かめた〔A-介入〕[Bittner2017]。STDP は多数回の経験による学習、BTSP は一回の経験による学習を担う、という整理がある〔総説〕[Liao2024][Magee2020]
- **似た経験を分ける（パターン分離）**：環境の形を少し変えると、歯状回・CA3 の発火の組み合わせが大きく変わった〔A-観察〕[Leutgeb2007]。歯状回だけで NMDA 受容体を欠くマウスは、似た二つの文脈をすばやく区別できなかった〔A-介入〕[McHugh2007]。ヒトでも、よく似た物を見たとき、CA3／歯状回の領域の応答がそれを別物として扱った〔H-観察〕[Bakker2008]
- **場所と時間の符号**：海馬には、場所に応じて発火する細胞〔A-観察〕[OKeefe1971]と、出来事のあいだの時間の経過に応じて順に発火する「時間細胞」がある〔A-観察〕[MacDonald2011]。海馬を損傷したラットは、においの一つひとつは覚えていても、その順序を覚えられなかった〔A-介入〕[Fortin2002]
- **どのニューロンが記録に参加するか**：学習の直前に興奮しやすい状態にあったニューロンが、記憶の痕跡（エングラム）に選ばれやすい〔A-介入〕[Han2007][Yiu2014]。近い時刻に学んだ二つの記憶は、重なったニューロンの集団を共有し、互いに結びついた〔A-介入〕[Cai2016]。エングラムの考え方は総説 [Josselyn2020] にまとまっている

### 1.2 証拠の強さ

| 主張 | 証拠 | 強さと限界 |
|---|---|---|
| 海馬系が新しいエピソードの形成に必要 | 〔H-損傷〕〔A-介入〕 | 強い。ただし損傷の範囲は揃わない。技能の学習などは別の系 |
| シナプスの可塑性が学習に関わる | 〔A-生理〕〔A-介入〕 | 強いが、阻害は学習の一部の成分だけを損なうことがある [Bannerman1995] |
| STDP が生体内の学習の主な規則 | 〔A-生理〕 | スライスでの現象。生体内でどの程度使われるかは条件に依る |
| 一回で書き込む可塑性（BTSP） | 〔A-介入〕 | 海馬 CA1・マウスで強い。ほかの部位・ヒトでの一般性は未確立 |
| 似た経験の分離に歯状回が関わる | 〔A-介入〕〔A-観察〕〔H-観察〕 | 複数の方法で一致。ただしヒトは相関の証拠 |
| 興奮しやすさが参加するニューロンを決める | 〔A-介入〕 | 扁桃体・海馬の恐怖条件づけなど、限られた課題 |

### 1.3 計算論的な解釈

- **一回で書き込む系**：まばらで、重なりの少ない符号に、一回で書き込めば、似た経験どうしの干渉を抑えながら素早く覚えられる〔理論〕[Marr1971][Treves1994]。歯状回は「重なりを減らす」役、CA3 の再帰結合は「結びつけて後で補完する」役、という分担が提案されている
- **時間の順序**：時刻の差に依存する可塑性は、「どちらが先か」を接続の向きに書き込む。数秒の窓の可塑性（BTSP）は、行動の時間尺度の出来事を結びつける
- **参加の選択**：興奮しやすさによる選択は、記憶の痕跡の大きさを一定に保ち、近い時刻の経験を結びつける仕組みとして解釈されている [Josselyn2020]

### 1.4 未解決

- 秒〜分の時間尺度の順序が、どの可塑性の組み合わせで書き込まれるか
- ヒトで、一回で書き込む可塑性がどこで・どう働くか
- 分離（似た経験を分ける）と、一般化（共通点をまとめる）の釣り合いがどう決まるか（§4 と関わる）

### 1.5 AnIma-ll で保存すべき因果関係の候補

| 番号 | 候補 | 札 | 理由 |
|---|---|---|---|
| Enc1 | 似た二つの経験が、内部で別の状態の変化として残ること（分離） | 【働き：強い候補】〔機構：代替あり〕 | 個別の出来事を区別して覚えることは、人間のエピソード記憶の定義に含まれる [Tulving2002]。分離の働きは、まばらな符号や直交化など、歯状回と違う構造でも作れる [Marr1971] |
| Enc2 | 一回の経験で、後に使える大きさの変化が起きうること | 【働き：強い候補】〔機構：代替あり〕 | 人間は一度の出来事を覚える。一回の書き込みは、外部の記憶を持つ人工のネットワークでも実現されている [Graves2016]。ただしそれが原則（意味を外に置かない）を満たすかは別に監査する |
| Enc3 | 経験の順序・時間の間隔が、内部の状態の違いとして残ること | 【働き：強い候補】〔機構：未決〕 | 「いつ・どの順で」はエピソード記憶の中心 [Tulving2002][Fortin2002]。現行の Core では、1 本の重みに時間差が混ざる（再評価 §3.1、識別のメモ 命題 3.3） |
| Enc4 | 記録に参加する部品が、その時の内部の状態で選ばれること | 【働き：候補】〔機構：未決〕 | 生物で実在し、近い時刻の経験を結ぶ働きがある [Cai2016]。必須かの根拠は弱い |

---

## 2. 保持・固定化：学習による変化が、どう安定するか

### 2.1 生物学的知見

- **シナプスの固定化**：短く続く LTP が長く続く LTP になるには、タンパク質の合成が要る。弱い刺激で「印」の付いたシナプスは、近い時間に別の強い刺激で作られたタンパク質を取り込んで長く続く（シナプスの印づけと捕獲）〔A-生理〕[Frey1997]
- **系の固定化**：海馬の損傷では、損傷の直前の記憶ほど失われやすく、古い記憶ほど残りやすい（時間的な勾配）〔H-損傷〕[Scoville1957][Squire2015]。これを「記憶は時間とともに海馬から大脳皮質へ移る」と見る標準的な見方と、「詳しいエピソードには海馬が残って関わり続ける」と見る見方がある〔総説〕[Frankland2005][Nadel1997]
- **固定化の回路**：マウスでは、学習の時点で前頭前野にもエングラムができるが、初めは自然には働かない「未熟」な状態で、時間とともに成熟した。海馬のエングラムは逆に働かなくなっていった〔A-介入〕[Kitamura2017]。2025 年の研究では、海馬の中でもエングラムの回路が時間とともに組み替わり、詳しい記憶から要点の記憶へ移った。これは成体の神経新生に依存し、新生を止めると組み替えが起きず詳しい記憶が残った〔A-介入〕[Ko2025]
- **睡眠中の再活性化**：学習中に一緒に発火した海馬の細胞の組は、その後の睡眠中にも一緒に発火しやすかった〔A-観察〕[Wilson1994]。睡眠中・休息中の海馬の鋭波リップル（再活性化が起きる短い振動）を電気刺激で抑えると、空間の学習が損なわれた〔A-介入〕[Girardeau2009][EgoStengel2010]。逆に、海馬と皮質の振動のタイミングを合わせる刺激で、記憶が良くなった〔A-介入〕[Maingret2016]
- **ヒトの睡眠**：学習中に嗅いだにおいを、深い睡眠中に再び嗅がせると、翌日の記憶が良くなった〔H-介入〕[Rasch2007]。睡眠中のゆっくりした脳波に合わせて音を鳴らし、その波を強めると、記憶の保持が良くなった〔H-介入〕[Ngo2013]
- **何を残すかの選択**：情動が高まった経験は、扁桃体とストレスホルモン（ノルアドレナリンなど）の作用で、よく固定される〔H-観察〕〔A-介入〕[McGaugh2004]。新しさに応じたドーパミンが、海馬の記憶を長期に残すかを調整する、という説がある〔理論〕[Lisman2005]。マウスでは、青斑核から海馬に放出されるドーパミンが、日常的な出来事の記憶の持続を強めた〔A-介入〕[Takeuchi2016]
- **再固定化**：一度固定した恐怖の記憶を思い出させた直後に、扁桃体でタンパク質の合成を阻害すると、記憶が失われた。想起が、記憶を再び変えうる状態にする〔A-介入〕[Nader2000]
- **睡眠とシナプスの全体の調整**：起きている間に強まったシナプスを、睡眠中に全体として弱めて釣り合いを取る、という仮説がある〔理論〕〔総説〕[Tononi2014]。証拠には賛否がある

### 2.2 証拠の強さ

| 主張 | 証拠 | 強さと限界 |
|---|---|---|
| 長く続く変化にタンパク質の合成が要る | 〔A-生理〕〔A-介入〕 | 強い。分子の詳細は生物に特有 |
| 系の固定化（時間的な勾配） | 〔H-損傷〕〔A-介入〕 | 現象は強い。標準的な見方と、海馬が関わり続ける見方の対立は未決着 |
| 睡眠中の再活性化が固定化に寄与 | 〔A-観察〕〔A-介入〕〔H-介入〕 | 抑えると悪く、強めると良くなるので、因果の証拠として比較的強い。ただし、再活性化の内容のどこが効いたかは分かれていない |
| 情動・新しさによる選択 | 〔H-観察〕〔A-介入〕 | 強いが、課題と種に依る |
| 再固定化 | 〔A-介入〕 | 動物で強い。ヒトでの再現性は議論がある |

### 2.3 計算論的な解釈

- **安定性と可塑性の板ばさみ**：新しく学ぶには変わりやすく、古いものを保つには変わりにくい必要がある〔総説〕[Abraham2005]。上限のあるシナプスでは、新しい学習が古い記憶を早く消す。速い変数と遅い変数を組み合わせたシナプスの模型は、保持の期間と容量を大きく伸ばす〔理論〕[Fusi2005][Benna2016]
- **相補的学習システム**：速く学ぶ系（海馬）が個々の経験を覚え、それを繰り返し再生して、ゆっくり学ぶ系（皮質）に少しずつ混ぜて教える。そうすると、ゆっくり学ぶ系が古い知識を壊さずに新しい知識を取り込める〔理論〕[McClelland1995][Kumaran2016]
- **選択**：情動・新しさの信号は、「何を長く残すか」を経験の後に決める仕組みとして解釈されている

### 2.4 未解決

- 詳しいエピソードに、海馬が永久に必要か
- 睡眠中の再活性化の、どの成分（順序・どの組・タイミング）が固定化に効くか
- 何を残し、何を消すかの選択の基準が、どこまで一般的か
- ヒトでの再固定化の効果の範囲

### 2.5 AnIma-ll で保存すべき因果関係の候補

| 番号 | 候補 | 札 | 理由 |
|---|---|---|---|
| Con1 | 変化の持続に、速く変わって消えやすい成分と、ゆっくりで安定な成分があること | 【働き：強い候補】〔機構：代替あり〕 | 新しく学ぶことと保つことの両立は、記憶一般の要件 [Abraham2005][Benna2016]。タンパク質の合成という生物の手段は必須ではない |
| Con2 | どの変化を長く残すかが、経験の後の内部の過程で選ばれること | 【働き：候補】〔機構：未決〕 | 人間では情動・新しさが選択に効く [McGaugh2004][Takeuchi2016]。選択の信号を何にするかは、原則 §6 の順序（価値は後）と関わる |
| Con3 | 入力のない時間の内部の活動が、保持・統合を変えること | 【働き：候補】〔機構：代替あり〕 | 動物とヒトで因果の証拠がある [Girardeau2009][Rasch2007]。AnIma-ll の「入力がなくても内部が動き続ける」と接続する。ただし、それを再活性化・リプレイと呼べるかは、識別のメモの R（対応の規則）が決まるまで判断しない。人工のネットワークでは、記録の再生（リプレイの緩衝）でも同様の働きが作られる [Kumaran2016] |
| Con4 | 想起が、記憶を再び変えうる状態にすること | 【未決】〔機構：未決〕 | 動物で実在 [Nader2000]。人間同等の目標に必要かは判断材料が足りない |

**現行 Core との関係**（再評価 §3.1 より）：今の可塑性の規則では、発火の組がなければ重みは変わらず、無活動の組は実効的に凍結して残る。速い成分と遅い成分の区別も、何を残すかの選択もない。

---

## 3. 想起・再構成：部分的な手がかりから、活動がどう再び形づくられるか

### 3.1 生物学的知見

- **部分的な手がかりからの補完**：CA3 だけで NMDA 受容体を欠くマウスは、手がかりが揃っていれば場所を思い出せたが、手がかりの一部を取り除くと思い出せなかった〔A-介入〕[Nakazawa2002]
- **エングラムの再活性化だけで想起が起きる**：恐怖の学習のときに働いた歯状回の細胞を印づけ、別の場所で光で活性化すると、マウスはすくんだ（恐怖の想起に当たる行動）〔A-介入〕[Liu2012]。別の場所での電気ショックの最中に元の場所のエングラムを活性化すると、経験していない「偽の記憶」ができた〔A-介入〕[Ramirez2013]
- **保持と取り出しは別**：学習の直後にタンパク質の合成を阻害して、自然には思い出せなくした（健忘）マウスでも、エングラムの細胞を光で活性化すると記憶が現れた。情報は残っていて、取り出しの経路が損なわれていた〔A-介入〕[Ryan2015]
- **ヒトの想起は、経験時の活動の再出現を伴う**：単語を思い出す数秒前から、その単語のカテゴリーに特有の皮質の活動の型が現れた〔H-観察〕[Polyn2005]。てんかんの患者の頭蓋内記録で、映像を見たときに発火した海馬などの単一ニューロンが、その映像を自由に思い出すときに再び発火した〔H-観察〕[GelbardSagiv2008]
- **想起は再構成で、誤りを含む**：事故の映像を見た後の質問の言葉づかいで、速度の見積もりが変わり、なかったガラスの破片を「見た」と答える人が増えた〔H-観察〕[Loftus1974]。想起は、断片から組み立て直す過程で、未来の想像と同じ仕組みを共有する〔総説〕[Schacter2007]。海馬を損傷した患者は、新しい場面を想像することも難しかった〔H-損傷〕[Hassabis2007]
- **索引の理論**：海馬は、経験のときに働いた広い皮質の活動の組み合わせへの「索引」を持ち、それを再び働かせて皮質の活動を呼び戻す、という理論〔理論〕[Teyler1986][Teyler2007]

### 3.2 証拠の強さ

| 主張 | 証拠 | 強さと限界 |
|---|---|---|
| CA3 の再帰結合が部分的な手がかりからの補完に関わる | 〔A-介入〕〔理論〕 | 一つの遺伝子操作の結果。理論とは整合する |
| エングラムの活性化が想起の行動を起こすのに十分 | 〔A-介入〕 | マウスの恐怖の条件づけが中心。より複雑な記憶への一般化は未確立 |
| 保持と取り出しは分けられる | 〔A-介入〕 | 強い。ただし「残っていた情報」の中身の詳しさは未確定 |
| ヒトで経験時の活動が想起時に再び現れる | 〔H-観察〕 | 相関の証拠。再出現が想起を起こしたかは示していない |
| 想起は再構成で、誤りを含む | 〔H-観察〕〔H-損傷〕 | 行動の証拠は強い |

### 3.3 計算論的な解釈

- **アトラクター**：再帰結合のネットワークは、覚えた活動の型を「落ち着き先」として持ち、一部の手がかりから全体に落ち着く（補完）〔理論〕[Hopfield1982][Marr1971]
- **索引と再構成**：小さな索引が、広く分散した表現の組み合わせを呼び戻す〔理論〕[Teyler1986]。足りない部分は、一般的な知識（スキーマ）で埋めるので、誤りが生じる [Schacter2007]

### 3.4 未解決

- どれだけの詳しさが保存され、どれだけが想起のときに組み立てられるか
- 手がかりがどう選ばれ、どの記憶が呼び戻されるかの競合
- 「働かないエングラム」（保持はあるが自然に取り出せない状態）の一般性

### 3.5 AnIma-ll で保存すべき因果関係の候補

| 番号 | 候補 | 札 | 理由 |
|---|---|---|---|
| Rec1 | 部分的な手がかりから、経験時の内部の活動の一部が再び形づくられること（補完） | 【働き：強い候補】〔機構：代替あり〕 | 人間の想起の中核 [Nakazawa2002][GelbardSagiv2008]。アトラクターや索引など、生物と違う構造でも補完は作れる [Hopfield1982] |
| Rec2 | 保持（変化が残っていること）と取り出し（その変化が活動を再び形づくれること）を、別々に観測・識別できること | 【働き：強い候補】（識別の要件） | [Ryan2015] の区別。再評価の E4・E6（接続の変化と活動の変化を同一視しない）と同じ |
| Rec3 | 想起が組み立て直しで、誤りを含みうること | 【未決】 | 人間の記憶の性質。「人間と同等以上」の目標で、誤りまで再現するのか、減らすのかは判断が要る |
| Rec4 | 想起と未来の想像が、同じ仕組みを使うこと | 【働き：候補】〔機構：未決〕 | [Hassabis2007][Schacter2007]。記憶の利用（§6）とつながる |

---

## 4. 連想・一般化：複数の経験から、共通の構造をどう得るか

### 4.1 生物学的知見

- **エピソードと知識は分かれうる**：幼いころに海馬を損傷した 3 人の患者は、日々の出来事をひどく忘れたのに、学校に通い、言葉や事実の知識を身につけた〔H-損傷〕[VarghaKhadem1997]。前側頭葉が萎縮する意味性認知症では、概念の知識そのものが失われていく〔H-損傷〕[Patterson2007]
- **スキーマがあると速く固定される**：ラットに、においと場所の組の「体系」を何週間も学ばせると、新しい組は一度で覚えられ、48 時間後には海馬を損傷しても忘れなかった〔A-介入〕[Tse2007]
- **関係からの推論**：海馬系を損なったラットは、A>B、B>C のような組は学べたが、直接学んでいない A>C を推論できなかった〔A-介入〕[Dusek1997]。ヒトでは、新しいことを学ぶときに重なる古い記憶が呼び戻されるほど、後の推論がうまくいった〔H-観察〕[Zeithamova2012]
- **詳しさから要点へ**：マウスで、時間とともに海馬のエングラムが組み替わり、元と違う状況でも働くようになった（一般化）[Ko2025]〔A-介入〕（§2.1）
- **認知地図**：迷路のラットは、報酬に結びついた反応の連鎖だけでなく、空間の地図のようなものを学ぶ、という古典的な主張〔A-観察：動物の行動実験の古典。脳への介入はない〕[Tolman1948]。海馬・嗅内皮質の符号は、空間だけでなく抽象的な関係の地図も作る、という総説〔総説〕[Behrens2018]

### 4.2 証拠の強さ

| 主張 | 証拠 | 強さと限界 |
|---|---|---|
| エピソードと意味の知識は部分的に別の基盤を持つ | 〔H-損傷〕 | 強いが、患者数が少ない |
| スキーマが固定化を速める | 〔A-介入〕 | 一つの課題系。一般性は追試が要る |
| 関係からの推論に海馬系が必要 | 〔A-介入〕〔H-観察〕 | 動物で因果、ヒトで相関 |
| 時間とともに一般化が進む | 〔A-介入〕 | 新しい結果（2025 年）。追試を待つ |

### 4.3 計算論的な解釈

- **相補的学習システム**：個々の経験を速く覚える系と、多くの経験に共通する統計をゆっくり学ぶ系の分担〔理論〕[McClelland1995][Kumaran2016]。海馬の中にも、個別の記憶を担う経路と、統計を学ぶ経路の分担がある、という模型もある〔理論〕[Schapiro2017]
- **予測の地図**：今の状態から、次にどの状態へ行きやすいかを学んだ表現（後続表現）は、海馬の場所細胞の性質を説明し、新しい目標への計画を速くする〔理論〕[Stachenfeld2017]
- **推論の二つの道**：学ぶときに重なる記憶をまとめておく（統合）か、使うときに別々の記憶を組み合わせる（想起のときの推論）か [Zeithamova2012]

### 4.4 未解決

- 個別の記憶と一般化した知識の分担が、二つの系を必要とするのか、一つの系の中で起きるのか
- 一般化がいつ起き、何が「共通の構造」として抜き出されるか
- 詳しさと要点の釣り合いを、何が決めるか

### 4.5 AnIma-ll で保存すべき因果関係の候補

| 番号 | 候補 | 札 | 理由 |
|---|---|---|---|
| Gen1 | 複数の経験に共通する構造が、個々の経験の記録とは別の内部の状態として形成されること | 【働き：強い候補】〔機構：未決〕 | 人間の意味記憶・知識に当たる [VarghaKhadem1997][Patterson2007] |
| Gen2 | 個別の経験と一般化した知識の両方が残り、互いに影響すること（速い学習と遅い学習） | 【働き：強い候補】〔機構：未決〕 | [McClelland1995][Tse2007]。二つの別の系が必要かは未決 [Schapiro2017] |
| Gen3 | 直接経験していない関係を、記憶の組み合わせで推論できること | 【働き：候補】〔機構：未決〕 | [Dusek1997][Zeithamova2012] |

**現行 Core との関係**：学習の通り道は組ごとの 3 値で（識別のメモ 命題 3.3）、刺激の同一性は配線が与える（再評価 §3.1）。共通の構造を、個別の記録と別に形成する場はない。

---

## 5. 干渉・忘却：新しい学習と過去の記憶は、どう共存するか

### 5.1 生物学的知見

- **忘却の曲線**：覚えた直後に速く忘れ、その後はゆっくり忘れる。19 世紀の Ebbinghaus の結果は、現代の追試でも再現された〔H-観察〕[Murre2015]
- **想起が別の記憶を忘れさせる**：ある項目を繰り返し思い出す練習をすると、同じ手がかりに結びついた別の項目が思い出しにくくなる〔H-観察〕[Anderson1994]
- **能動的な忘却の仕組み**：ショウジョウバエでは、Rac という分子の活動を抑えると忘却が遅くなり、強めると速くなった〔A-介入〕[Shuai2010]。マウスでは、学習の後に海馬の神経新生を増やすと忘却が進み、幼い時期に新生を減らすと忘却が減った〔A-介入〕[Akers2014]。忘却は記憶の失敗ではなく、変化する世界への適応や一般化のための働きでもある、という総説〔総説〕[Davis2017][Richards2017]
- **特定の記憶の痕跡を消す**：運動の学習で強まったシナプスの突起に印を付け、光で縮めると、その学習が消えた〔A-介入〕[HayashiTakagi2015]

### 5.2 証拠の強さ

| 主張 | 証拠 | 強さと限界 |
|---|---|---|
| 忘却の時間経過 | 〔H-観察〕 | 強い（行動の現象） |
| 想起による抑制 | 〔H-観察〕 | 行動の現象として広く再現。機構の説明には議論 |
| 能動的な忘却の分子・細胞の仕組み | 〔A-介入〕 | ハエ・マウスで強い。ヒトでの対応は未確立 |
| シナプスの痕跡を消すと学習が消える | 〔A-介入〕 | マウスの運動皮質の一つの課題 |

### 5.3 計算論的な解釈

- **破局的な干渉**：普通の人工ニューラルネットワークは、新しい課題を順に学ぶと、前の課題を急に忘れる〔理論〕[McCloskey1989]。対策として、古い課題に大事な重みを変わりにくくする方法〔理論〕[Kirkpatrick2017]、古い経験を混ぜて再学習する方法（相補的学習システム）[McClelland1995] がある
- **時間尺度の多い保持**：変わりやすい成分と変わりにくい成分を組み合わせると、新しい学習と古い記憶の保持を両立しやすい〔理論〕[Fusi2005][Benna2016]
- **忘却の役割**：古くなった詳細を薄めると、変化する環境への適応と一般化が良くなる、という見方〔総説〕[Richards2017]

### 5.4 未解決

- 人間の忘却のうち、保存の消失と、取り出しの失敗の割合
- 能動的な忘却を、何が・いつ起こすか
- 人工のシステムで、干渉を避ける方法のどれが、人間の記憶に近いか

### 5.5 AnIma-ll で保存すべき因果関係の候補

| 番号 | 候補 | 札 | 理由 |
|---|---|---|---|
| Fgt1 | 新しい学習が、古い記憶を全面的には壊さないこと | 【働き：強い候補】〔機構：代替あり〕 | 長く生きる個体には必須に近い。対策は生物以外の方法でも作られている [Kirkpatrick2017][McClelland1995] |
| Fgt2 | 忘却を、失敗ではなく内部の過程（弱める・取り出しを抑える）として持つこと | 【働き：候補】〔機構：未決〕 | 生物で実在し、働きがある [Davis2017][Richards2017]。「人間以上」の目標とどう両立させるかは判断が要る |
| Fgt3 | 保存が失われたのか、取り出せないだけかを区別できること | 【働き：強い候補】（識別の要件） | §3 の Rec2 と同じ |

**現行 Core との関係**：再評価 §2.1 のとおり、0015 では、入力のない時間の自発の活動で、経験の差の多くが縮んだ（同じ向きのまま縮んだ個体が多い）。古い変化を守る仕組みはない。

---

## 6. 記憶の利用：保存された経験が、今の認知・行動にどう因果的に作用するか

### 6.1 生物学的知見

- **思い出さなくても使われる記憶**：パーキンソン病の患者は、確率的な分類の課題（習慣の学習）を学べなかったが、課題の場面のことは覚えていた。健忘の患者は逆に、分類は学べたが、場面を覚えていなかった〔H-損傷〕[Knowlton1996]。宣言的な記憶と習慣の記憶は、別の基盤（海馬系と線条体）に依存する
- **未来の道を描く**：ラットが目標へ向かう前に、海馬の場所細胞の発火の列が、これから進む道を先取りして描いた〔A-観察〕[Pfeiffer2013]。起きている間の鋭波リップルを抑えると、空間の作業記憶を要する選択（直前にいた腕を覚えて次の腕を選ぶ）の成績が上がりにくくなった〔A-介入〕[Jadhav2012]
- **想像と計画**：海馬の健忘の患者は、新しい場面を想像することも難しかった〔H-損傷〕[Hassabis2007]
- **エピソードを使う判断**：個々の過去の経験を思い出して今の選択に使う仕組みと、経験から平均的な価値を学ぶ仕組みが、ヒトと動物の両方で併用されている、という総説〔総説〕[Gershman2017]
- **短い時間の保持（作業記憶）**：サルの前頭前野のニューロンが、覚えた位置に応じて、遅延のあいだ発火を続けた〔A-観察〕[Funahashi1989]〔総説〕[GoldmanRakic1995]。一方、発火を続けなくても、短期のシナプスの変化で情報を保てる、という模型と証拠もある〔理論〕〔総説〕[Mongillo2008][Stokes2015]
- **情動と記憶の利用**：情動の高い経験の記憶は、強く固定され、後の行動を強く方向づける [McGaugh2004]

### 6.2 証拠の強さ

| 主張 | 証拠 | 強さと限界 |
|---|---|---|
| 宣言的な記憶と習慣の記憶の解離 | 〔H-損傷〕 | 強い（二重解離） |
| 海馬の活動の列が、未来の行動の計画に関わる | 〔A-観察〕〔A-介入〕 | 観察は強い。介入は課題が限られる |
| 想起と想像の共通の基盤 | 〔H-損傷〕〔H-観察〕 | 強いが、損傷の範囲が揃わない |
| 作業記憶の実現（持続する発火か、シナプスか） | 〔A-観察〕〔理論〕 | 論争中 |

### 6.3 計算論的な解釈

- **使い方の複数の道**：①思い出さずに処理を変える（習慣・技能・予期）、②思い出した内容を今の判断に入れる（エピソードによる判断）、③記憶から未来を組み立てて、行動の前に評価する（計画）〔総説〕[Gershman2017][Behrens2018]
- **地図と計画**：経験から作った関係の地図の上で、まだ通っていない道を組み立てる〔理論〕[Tolman1948][Stachenfeld2017]

### 6.4 未解決

- 記憶の内容が、どの経路で行動の選択に入るか
- 作業記憶の実現（持続する発火か、短期のシナプスの変化か）
- 計画のときの海馬の活動の列が、どこまで記憶の再生で、どこまで新しい組み立てか

### 6.5 AnIma-ll で保存すべき因果関係の候補

| 番号 | 候補 | 札 | 理由 |
|---|---|---|---|
| Use1 | 記憶が、明示的に思い出すことなしに、後の処理（感じ方・予期・反応の傾向）を変えること | 【働き：強い候補】〔機構：代替あり〕 | 習慣・技能の記憶 [Knowlton1996]。原則 R3（経験による変形）と同じ。現行の Core にも部分的にある（0014・0016〜0019 は介入の上で確認） |
| Use2 | 想起された内容が、今の内部の活動に入り、次の判断・行動の意図を変えること | 【働き：強い候補】〔機構：未決〕 | 記憶を「本人が使う」ことの中心。原則 R6（行動の意図は内部の状態から）が前提で、現行は未実装 |
| Use3 | 記憶から未来の状況を組み立て、行動の前に評価すること | 【働き：候補】〔機構：未決〕 | [Pfeiffer2013][Hassabis2007]。原則 §6 の 6・7（閉ループ・価値）の段階と関わる |
| Use4 | 短い時間の保持（作業記憶）を、持続する活動か、短期の変化で持つこと | 【未決】〔機構：未決〕 | 実現の方法は生物でも論争中 |

---

## 7. DB の役割と、神経回路の内部状態との因果的な境界（決定しない）

ChatGPT の必須条件 3 に従い、DB の三つの候補（#95 §3）について、内部の状態との因果的な境界を検討するだけにとどめる。

| 候補 | 人間での近い例 | 内部の状態との境界の問い | 原則との関係 |
|---|---|---|---|
| **永続化**（内部の状態を保存して戻す） | 該当なし（脳は止まらない） | 保存した状態を戻したとき、止めずに進んだ場合と同じ経路をたどるか。再評価 §1.2 のとおり、今のスナップショットは届く途中の駆動を含まない | 工学の機能。認知の意味を持たない（台帳 §3.4b と同じ種類の区別） |
| **外界の記録**（映像・音声・出来事の原資料を保つ） | メモ・写真・日記（外部の記憶） | 記録の中身は、どの経路で内部に入るか。感覚として再び経験する（写真を見る）のか、内部の表現に直接入るのか | 内部の表現に直接入れると、原則 §3 の「1 つの payload に完成した意味」「外部ラベル」に近づく |
| **経験への索引を支える** | 海馬の索引の理論 [Teyler1986] が近いが、脳の索引は神経回路そのもの | 何を取り出すかを、内部の状態が決めているか、検索の規則や外部モデルの埋め込みが決めているか | 外部モデルの埋め込みで検索して言語モデルに渡す方式（RAG [Lewis2020]）を内部の表現に使うと、原則 §3 の「embedding leakage」に当たりうる。検索の規則を人が書けば、想起の働きを外に押し出す |

- 人間も外部の記憶（メモ・写真）を使う。DB を使うこと自体は、人間らしさにも原則にも反しない
- ただし、**記録が保存されていることと、本人が想起できることは別**（§0.4、§3 の Rec2）。DB に記録があることを、AnIma-ll の記憶の成立の証拠にしない
- どの役割を採るか・組み合わせるかは決めない

---

## 8. まとめ：S1 に引き渡す比較の軸（Unit の構造は選ばない）

S1 で神経集団の Unit などの候補を比べるときに、「その候補で、次の働きの因果関係を保てるか」を軸にする。働きの一覧であって、機構の指定ではない。

| 軸 | 働き | 札 | 出どころ |
|---|---|---|---|
| MF1 | 似た経験の分離 | 【強い候補】 | Enc1 |
| MF2 | 一回の経験での書き込み | 【強い候補】 | Enc2 |
| MF3 | 順序・時間の間隔の保持 | 【強い候補】 | Enc3 |
| MF4 | 速い成分と遅い成分による保持と、何を残すかの選択 | 前半【強い候補】、選択は【候補】 | Con1・Con2 |
| MF5 | 入力のない時間の内部の活動による統合 | 【候補】 | Con3 |
| MF6 | 部分的な手がかりからの補完と、保持と取り出しの区別 | 【強い候補】 | Rec1・Rec2 |
| MF7 | 共通の構造の形成と、個別の記録との共存 | 【強い候補】 | Gen1・Gen2 |
| MF8 | 新しい学習による破局的な干渉の回避 | 【強い候補】 | Fgt1 |
| MF9 | 思い出さなくても処理を変えること、思い出した内容が判断に入ること | 【強い候補】 | Use1・Use2 |

- 【強い候補】は、目標「人間と同等以上の記憶機能」から働きとして求められる根拠が強いものだが、**採用の決定ではない**。どう実現するかは、ほぼすべて〔機構：代替あり〕か〔機構：未決〕である
- **特定の生物学的機構そのもの**（タンパク質の合成、成体の神経新生、鋭波リップル、BTSP、歯状回など）を「AnIma-ll に必須」とする根拠は、この調査の範囲では見つからなかった。どれも、ある働きの一つの実現として理解するのが妥当で、必須かは【未決】とする
- 一方で、**生物の機構は、「その働きが、どんな時間尺度で、どんな部品の組み合わせで実現できるか」の具体例**として、S1 の候補を比べるときの手本になる（#95 §0.1 の 2）

### 8.1 現行 3 Unit Core との対応（再評価 #94 の範囲で）

| 軸 | 現行 Core | 根拠 |
|---|---|---|
| MF1 分離 | 刺激の同一性は配線が与え、分離を形成する場がない | 再評価 §3.1 |
| MF2 一回の書き込み | 可塑性の振幅は小さく（A ＝ 0.01 × w_max）、多数回の組の累積で変わる | 再評価 §1.2 |
| MF3 順序 | 1 本の重みに時間差が混ざる。直接一段の遅延は 1 | 識別のメモ 命題 3.3、再評価 §3.1 |
| MF4 保持と選択 | 無活動では重みが凍結して残る。速い／遅い成分・選択はない | 再評価 §3.1 |
| MF5 入力のない時間 | 自発の活動はあるが、統合の働きは確かめていない（Q5 の L3 は未設計） | 再評価 §2.3 |
| MF6 補完 | 部分的な手がかりからの補完は確かめていない | — |
| MF7 共通の構造 | 学習の通り道は組ごとの 3 値 | 識別のメモ 命題 3.3 |
| MF8 干渉の回避 | 古い変化を守る仕組みはない（0015 で差の多くが縮んだ） | 再評価 §2.1 |
| MF9 利用 | 重みの差は、刺激への応答を変える（介入の上で確認）。行動の出口はない | 再評価 §2.3・§4.1 |

これは「3 Unit が足りない」という判定ではない（再評価 §2.4 (c) と同じ）。3 Unit は、現象を分離して調べる最小模型として作られた。上の表は、次の模型を比べる基準を揃えるためのものである。

---

## 9. 言わないこと

- 動物の特定の課題で必要だった回路・分子を、AnIma-ll に必須と呼ばない
- 再活性化・リプレイ・保持・想起・行動の変化を、同じものとして扱わない
- 【強い候補】を、採用が決まった仕様と呼ばない
- DB の役割を決めない。DB に記録があることを、記憶の成立と呼ばない
- この文書の比較の軸を、S1 の Unit の構造を選んだ結果と呼ばない（構造はまだ選んでいない）
- 相関の証拠（〔H-観察〕〔A-観察〕）を、因果の証拠と呼ばない

## 10. 未解決（S1 との往復の前に残ること）

1. 【強い候補】のそれぞれについて、「その働きがあるとどう確かめるか」（観測の契約）を、検出のしやすさで選ばずに書くこと（識別のメモ §0.1 と同じ規律）
2. 【未決】の候補（Con4 再固定化、Rec3 想起の誤り、Fgt2 能動的な忘却、Use4 作業記憶）を、目標「人間と同等以上」のどちらに寄せるか（人間の性質を再現するか、上回るか）の判断。t-k さんの判断が要る
3. 何を長く残すかの選択（Con2）の信号を、価値を使わずに作れるか（原則 §6・§8 の 1）
4. DB の三つの役割の、内部の状態との境界の具体的な契約

---

## 11. 専門知識がなくても読める解説（t-k さんへ）

### 人間の記憶は「保存」ではなく「変化」でできている

人間の脳には、出来事を書き込む専用の保存場所はありません。経験すると、ニューロンどうしのつながり方が少しずつ変わります。思い出すときは、その変わったつながりを手がかりに、経験したときの脳の活動の一部をもう一度組み立てます。

だから人間の記憶には、次のような性質があります。

- **少しの手がかりで全体がよみがえる**：においをかいだだけで、何年も前の夏を思い出す
- **思い出すたびに少し変わる**：聞かれ方しだいで、なかったものを「見た」と思い込むこともある
- **似た経験から「だいたいこうなる」という知識ができる**：何本も映画を見るうちに、「この監督の作品はこういう感じ」が分かってくる
- **忘れることも働きの一部**：細かいことを忘れるから、要点がまとまり、新しいことも覚えられる
- **思い出さなくても使われる**：自転車の乗り方は、思い出そうとしなくても体が覚えている
- **眠っている間に整理される**：睡眠中に、その日の経験のときの脳の活動の一部が再び現れ、それが記憶の定着を助けていると考えられている（動物とヒトの両方で、それを強めたり弱めたりする実験がある）

### なぜ「DB に大量に保存できる」だけでは、人間と同じ記憶にならないのか

例えば、t-k さんと AnIma-ll が一緒に映画を見たとします。DB には、映画の映像も会話もすべて保存できます。質問されれば「あの映画の 2 時間 3 分のところで…」と正確に答えられるでしょう。でも、それは人間の記憶とは違います。

1. **保存していることと、思い出すことは別です。** DB の中身は、誰かが検索しない限り何もしません。人間は、似た曲が流れただけで、頼まれてもいないのに映画のことを思い出します。何を思い出すかを、本人の中の状態が決めています
2. **記憶は、本人を変えます。** 人間は映画を見た後、同じ監督の次の作品の見方が変わります。記憶は「取り出す情報」である前に、「その後の感じ方や考え方の変化」です。DB に記録を足しても、本人の感じ方は変わりません
3. **人間は、たくさんの経験から共通点を自分で取り出します。** DB は一つひとつの記録を並べるだけで、共通点を勝手にはまとめません
4. **何を残すかを、本人が選んでいます。** 感動した場面ほど強く残り、どうでもいい場面は薄れます。DB は全部を同じように残します
5. **外から見た答えが同じでも、中身は違います。** 「LLM と DB」でも、人間らしい返事はできます。だから、返事だけ見ても区別がつきません。AnIma-ll では、「本人の中のどの変化が、その思い出しや反応を生んだか」まで確かめることを大事にしています

ただし、DB を使うことが悪いわけではありません。人間もメモや写真で記憶を補います。問題は、DB を「記憶そのもの」と呼んでしまうことです。DB は道具で、記憶は本人の中の変化と働き、と分けて考える、というのが今の立場です。

### この調査で分かったこと（一言で）

人間の記憶には、9 つくらいの大事な働きがあります。似た経験を区別する、一度で覚える、順番を覚える、長く残すものを選ぶ、眠っている間に整理する、少しの手がかりで思い出す、共通点をまとめる、新しく覚えても古いことを壊さない、思い出さなくても使う、です。

一方、脳がそれぞれを実現している「部品」（特定の分子や脳の部位）が、AnIma-ll にもそのまま必要だという根拠は見つかりませんでした。次は、「この 9 つの働きを、どんな部品なら保てるか」を考える段階（S1）です。

### t-k さんに決めてほしいこと（急ぎではありません）

人間の記憶には「思い出すたびに変わる」「誤って思い出す」「忘れる」という性質があります。「人間と同等以上」を目指すとき、これらも再現したいですか。それとも、人間より正確で忘れにくい記憶を目指しますか。

---

## 参考文献

DOI は 2026-10-14 に Crossref の登録情報と照合した。

### 記憶の系・ヒトの損傷

- [Scoville1957] Scoville, W. B., & Milner, B. (1957). Loss of recent memory after bilateral hippocampal lesions. *Journal of Neurology, Neurosurgery & Psychiatry*, 20, 11–21. https://doi.org/10.1136/jnnp.20.1.11 — H.M. の症例。〔H-損傷〕。単一の症例
- [Squire2004] Squire, L. R. (2004). Memory systems of the brain: A brief history and current perspective. *Neurobiology of Learning and Memory*, 82, 171–177. https://doi.org/10.1016/j.nlm.2004.06.005 — 〔総説〕
- [Tulving2002] Tulving, E. (2002). Episodic memory: From mind to brain. *Annual Review of Psychology*, 53, 1–25. https://doi.org/10.1146/annurev.psych.53.100901.135114 — 〔総説〕。エピソード記憶の定義
- [VarghaKhadem1997] Vargha-Khadem, F., et al. (1997). Differential effects of early hippocampal pathology on episodic and semantic memory. *Science*, 277, 376–380. https://doi.org/10.1126/science.277.5324.376 — 〔H-損傷〕。3 人の患者
- [Patterson2007] Patterson, K., Nestor, P. J., & Rogers, T. T. (2007). Where do you know what you know? The representation of semantic knowledge in the human brain. *Nature Reviews Neuroscience*, 8, 976–987. https://doi.org/10.1038/nrn2277 — 〔総説〕。意味性認知症
- [Knowlton1996] Knowlton, B. J., Mangels, J. A., & Squire, L. R. (1996). A neostriatal habit learning system in humans. *Science*, 273, 1399–1402. https://doi.org/10.1126/science.273.5280.1399 — 〔H-損傷〕。二重解離

### 符号化

- [Bliss1973] Bliss, T. V. P., & Lømo, T. (1973). Long-lasting potentiation of synaptic transmission in the dentate area of the anaesthetized rabbit following stimulation of the perforant path. *The Journal of Physiology*, 232, 331–356. https://doi.org/10.1113/jphysiol.1973.sp010273 — 〔A-生理〕
- [Morris1986] Morris, R. G. M., Anderson, E., Lynch, G. S., & Baudry, M. (1986). Selective impairment of learning and blockade of long-term potentiation by an N-methyl-D-aspartate receptor antagonist, AP5. *Nature*, 319, 774–776. https://doi.org/10.1038/319774a0 — 〔A-介入〕
- [Bannerman1995] Bannerman, D. M., Good, M. A., Butcher, S. P., Ramsay, M., & Morris, R. G. M. (1995). Distinct components of spatial learning revealed by prior training and NMDA receptor blockade. *Nature*, 378, 182–186. https://doi.org/10.1038/378182a0 — 〔A-介入〕。[Morris1986] の範囲を限定
- [Markram1997] Markram, H., Lübke, J., Frotscher, M., & Sakmann, B. (1997). Regulation of synaptic efficacy by coincidence of postsynaptic APs and EPSPs. *Science*, 275, 213–215. https://doi.org/10.1126/science.275.5297.213 — 〔A-生理〕
- [Bi1998] Bi, G., & Poo, M. (1998). Synaptic modifications in cultured hippocampal neurons: Dependence on spike timing, synaptic strength, and postsynaptic cell type. *The Journal of Neuroscience*, 18, 10464–10472. https://doi.org/10.1523/JNEUROSCI.18-24-10464.1998 — 〔A-生理〕。培養細胞
- [Bittner2017] Bittner, K. C., Milstein, A. D., Grienberger, C., Romani, S., & Magee, J. C. (2017). Behavioral time scale synaptic plasticity underlies CA1 place fields. *Science*, 357, 1033–1036. https://doi.org/10.1126/science.aan3846 — 〔A-介入〕。マウス CA1
- [Magee2020] Magee, J. C., & Grienberger, C. (2020). Synaptic plasticity forms and functions. *Annual Review of Neuroscience*, 43, 95–117. https://doi.org/10.1146/annurev-neuro-090919-022842 — 〔総説〕
- [Liao2024] Liao, Z., & Losonczy, A. (2024). Learning, fast and slow: Single- and many-shot learning in the hippocampus. *Annual Review of Neuroscience*, 47. https://doi.org/10.1146/annurev-neuro-102423-100258 — 〔総説〕。STDP と BTSP の役割分担
- [Leutgeb2007] Leutgeb, J. K., Leutgeb, S., Moser, M.-B., & Moser, E. I. (2007). Pattern separation in the dentate gyrus and CA3 of the hippocampus. *Science*, 315, 961–966. https://doi.org/10.1126/science.1135801 — 〔A-観察〕
- [McHugh2007] McHugh, T. J., et al. (2007). Dentate gyrus NMDA receptors mediate rapid pattern separation in the hippocampal network. *Science*, 317, 94–99. https://doi.org/10.1126/science.1140263 — 〔A-介入〕
- [Bakker2008] Bakker, A., Kirwan, C. B., Miller, M., & Stark, C. E. L. (2008). Pattern separation in the human hippocampal CA3 and dentate gyrus. *Science*, 319, 1640–1642. https://doi.org/10.1126/science.1152882 — 〔H-観察〕。fMRI
- [OKeefe1971] O'Keefe, J., & Dostrovsky, J. (1971). The hippocampus as a spatial map. Preliminary evidence from unit activity in the freely-moving rat. *Brain Research*, 34, 171–175. https://doi.org/10.1016/0006-8993(71)90358-1 — 〔A-観察〕
- [MacDonald2011] MacDonald, C. J., Lepage, K. Q., Eden, U. T., & Eichenbaum, H. (2011). Hippocampal "time cells" bridge the gap in memory for discontiguous events. *Neuron*, 71, 737–749. https://doi.org/10.1016/j.neuron.2011.07.012 — 〔A-観察〕
- [Fortin2002] Fortin, N. J., Agster, K. L., & Eichenbaum, H. B. (2002). Critical role of the hippocampus in memory for sequences of events. *Nature Neuroscience*, 5, 458–462. https://doi.org/10.1038/nn834 — 〔A-介入〕
- [Han2007] Han, J.-H., et al. (2007). Neuronal competition and selection during memory formation. *Science*, 316, 457–460. https://doi.org/10.1126/science.1139438 — 〔A-介入〕。扁桃体
- [Yiu2014] Yiu, A. P., et al. (2014). Neurons are recruited to a memory trace based on relative neuronal excitability immediately before training. *Neuron*, 83, 722–735. https://doi.org/10.1016/j.neuron.2014.07.017 — 〔A-介入〕
- [Cai2016] Cai, D. J., et al. (2016). A shared neural ensemble links distinct contextual memories encoded close in time. *Nature*, 534, 115–118. https://doi.org/10.1038/nature17955 — 〔A-介入〕
- [Josselyn2020] Josselyn, S. A., & Tonegawa, S. (2020). Memory engrams: Recalling the past and imagining the future. *Science*, 367, eaaw4325. https://doi.org/10.1126/science.aaw4325 — 〔総説〕
- [Marr1971] Marr, D. (1971). Simple memory: A theory for archicortex. *Philosophical Transactions of the Royal Society of London. B*, 262, 23–81. https://doi.org/10.1098/rstb.1971.0078 — 〔理論〕
- [Treves1994] Treves, A., & Rolls, E. T. (1994). Computational analysis of the role of the hippocampus in memory. *Hippocampus*, 4, 374–391. https://doi.org/10.1002/hipo.450040319 — 〔理論〕

### 保持・固定化

- [Frey1997] Frey, U., & Morris, R. G. M. (1997). Synaptic tagging and long-term potentiation. *Nature*, 385, 533–536. https://doi.org/10.1038/385533a0 — 〔A-生理〕
- [Squire2015] Squire, L. R., Genzel, L., Wixted, J. T., & Morris, R. G. (2015). Memory consolidation. *Cold Spring Harbor Perspectives in Biology*, 7, a021766. https://doi.org/10.1101/cshperspect.a021766 — 〔総説〕
- [Frankland2005] Frankland, P. W., & Bontempi, B. (2005). The organization of recent and remote memories. *Nature Reviews Neuroscience*, 6, 119–130. https://doi.org/10.1038/nrn1607 — 〔総説〕
- [Nadel1997] Nadel, L., & Moscovitch, M. (1997). Memory consolidation, retrograde amnesia and the hippocampal complex. *Current Opinion in Neurobiology*, 7, 217–227. https://doi.org/10.1016/S0959-4388(97)80010-4 — 〔総説〕。多重痕跡の理論
- [Kitamura2017] Kitamura, T., et al. (2017). Engrams and circuits crucial for systems consolidation of a memory. *Science*, 356, 73–78. https://doi.org/10.1126/science.aam6808 — 〔A-介入〕
- [Ko2025] Ko, S. Y., Rong, Y., Ramsaran, A. I., et al., Josselyn, S. A., & Frankland, P. W. (2025). Systems consolidation reorganizes hippocampal engram circuitry. *Nature*, 643, 735–743. https://doi.org/10.1038/s41586-025-08993-1 — 〔A-介入〕。マウス。追試を待つ
- [Wilson1994] Wilson, M. A., & McNaughton, B. L. (1994). Reactivation of hippocampal ensemble memories during sleep. *Science*, 265, 676–679. https://doi.org/10.1126/science.8036517 — 〔A-観察〕
- [Girardeau2009] Girardeau, G., Benchenane, K., Wiener, S. I., Buzsáki, G., & Zugaro, M. B. (2009). Selective suppression of hippocampal ripples impairs spatial memory. *Nature Neuroscience*, 12, 1222–1223. https://doi.org/10.1038/nn.2384 — 〔A-介入〕
- [EgoStengel2010] Ego-Stengel, V., & Wilson, M. A. (2010). Disruption of ripple-associated hippocampal activity during rest impairs spatial learning in the rat. *Hippocampus*, 20, 1–10. https://doi.org/10.1002/hipo.20707 — 〔A-介入〕（オンライン公開は 2009 年）
- [Maingret2016] Maingret, N., Girardeau, G., Todorova, R., Goutierre, M., & Zugaro, M. (2016). Hippocampo-cortical coupling mediates memory consolidation during sleep. *Nature Neuroscience*, 19, 959–964. https://doi.org/10.1038/nn.4304 — 〔A-介入〕
- [Rasch2007] Rasch, B., Büchel, C., Gais, S., & Born, J. (2007). Odor cues during slow-wave sleep prompt declarative memory consolidation. *Science*, 315, 1426–1429. https://doi.org/10.1126/science.1138581 — 〔H-介入〕
- [Ngo2013] Ngo, H.-V. V., Martinetz, T., Born, J., & Mölle, M. (2013). Auditory closed-loop stimulation of the sleep slow oscillation enhances memory. *Neuron*, 78, 545–553. https://doi.org/10.1016/j.neuron.2013.03.006 — 〔H-介入〕
- [Tononi2014] Tononi, G., & Cirelli, C. (2014). Sleep and the price of plasticity: From synaptic and cellular homeostasis to memory consolidation and integration. *Neuron*, 81, 12–34. https://doi.org/10.1016/j.neuron.2013.12.025 — 〔総説〕〔理論〕
- [Nader2000] Nader, K., Schafe, G. E., & LeDoux, J. E. (2000). Fear memories require protein synthesis in the amygdala for reconsolidation after retrieval. *Nature*, 406, 722–726. https://doi.org/10.1038/35021052 — 〔A-介入〕
- [McGaugh2004] McGaugh, J. L. (2004). The amygdala modulates the consolidation of memories of emotionally arousing experiences. *Annual Review of Neuroscience*, 27, 1–28. https://doi.org/10.1146/annurev.neuro.27.070203.144157 — 〔総説〕
- [Lisman2005] Lisman, J. E., & Grace, A. A. (2005). The hippocampal-VTA loop: Controlling the entry of information into long-term memory. *Neuron*, 46, 703–713. https://doi.org/10.1016/j.neuron.2005.05.002 — 〔理論〕〔総説〕
- [Takeuchi2016] Takeuchi, T., et al. (2016). Locus coeruleus and dopaminergic consolidation of everyday memory. *Nature*, 537, 357–362. https://doi.org/10.1038/nature19325 — 〔A-介入〕
- [Abraham2005] Abraham, W. C., & Robins, A. (2005). Memory retention – the synaptic stability versus plasticity dilemma. *Trends in Neurosciences*, 28, 73–78. https://doi.org/10.1016/j.tins.2004.12.003 — 〔総説〕
- [Fusi2005] Fusi, S., Drew, P. J., & Abbott, L. F. (2005). Cascade models of synaptically stored memories. *Neuron*, 45, 599–611. https://doi.org/10.1016/j.neuron.2005.02.001 — 〔理論〕
- [Benna2016] Benna, M. K., & Fusi, S. (2016). Computational principles of synaptic memory consolidation. *Nature Neuroscience*, 19, 1697–1706. https://doi.org/10.1038/nn.4401 — 〔理論〕

### 想起・再構成

- [Nakazawa2002] Nakazawa, K., et al. (2002). Requirement for hippocampal CA3 NMDA receptors in associative memory recall. *Science*, 297, 211–218. https://doi.org/10.1126/science.1071795 — 〔A-介入〕
- [Liu2012] Liu, X., et al. (2012). Optogenetic stimulation of a hippocampal engram activates fear memory recall. *Nature*, 484, 381–385. https://doi.org/10.1038/nature11028 — 〔A-介入〕
- [Ramirez2013] Ramirez, S., et al. (2013). Creating a false memory in the hippocampus. *Science*, 341, 387–391. https://doi.org/10.1126/science.1239073 — 〔A-介入〕
- [Ryan2015] Ryan, T. J., Roy, D. S., Pignatelli, M., Arons, A., & Tonegawa, S. (2015). Engram cells retain memory under retrograde amnesia. *Science*, 348, 1007–1013. https://doi.org/10.1126/science.aaa5542 — 〔A-介入〕
- [Polyn2005] Polyn, S. M., Natu, V. S., Cohen, J. D., & Norman, K. A. (2005). Category-specific cortical activity precedes retrieval during memory search. *Science*, 310, 1963–1966. https://doi.org/10.1126/science.1117645 — 〔H-観察〕
- [GelbardSagiv2008] Gelbard-Sagiv, H., Mukamel, R., Harel, M., Malach, R., & Fried, I. (2008). Internally generated reactivation of single neurons in human hippocampus during free recall. *Science*, 322, 96–101. https://doi.org/10.1126/science.1164685 — 〔H-観察〕。頭蓋内記録
- [Loftus1974] Loftus, E. F., & Palmer, J. C. (1974). Reconstruction of automobile destruction: An example of the interaction between language and memory. *Journal of Verbal Learning and Verbal Behavior*, 13, 585–589. https://doi.org/10.1016/S0022-5371(74)80011-3 — 〔H-観察〕（行動）
- [Schacter2007] Schacter, D. L., & Addis, D. R. (2007). The cognitive neuroscience of constructive memory: Remembering the past and imagining the future. *Philosophical Transactions of the Royal Society B*, 362, 773–786. https://doi.org/10.1098/rstb.2007.2087 — 〔総説〕
- [Hassabis2007] Hassabis, D., Kumaran, D., Vann, S. D., & Maguire, E. A. (2007). Patients with hippocampal amnesia cannot imagine new experiences. *Proceedings of the National Academy of Sciences*, 104, 1726–1731. https://doi.org/10.1073/pnas.0610561104 — 〔H-損傷〕
- [Hopfield1982] Hopfield, J. J. (1982). Neural networks and physical systems with emergent collective computational abilities. *Proceedings of the National Academy of Sciences*, 79, 2554–2558. https://doi.org/10.1073/pnas.79.8.2554 — 〔理論〕
- [Teyler1986] Teyler, T. J., & DiScenna, P. (1986). The hippocampal memory indexing theory. *Behavioral Neuroscience*, 100, 147–154. https://doi.org/10.1037/0735-7044.100.2.147 — 〔理論〕
- [Teyler2007] Teyler, T. J., & Rudy, J. W. (2007). The hippocampal indexing theory and episodic memory: Updating the index. *Hippocampus*, 17, 1158–1169. https://doi.org/10.1002/hipo.20350 — 〔理論〕〔総説〕

### 連想・一般化

- [McClelland1995] McClelland, J. L., McNaughton, B. L., & O'Reilly, R. C. (1995). Why there are complementary learning systems in the hippocampus and neocortex: Insights from the successes and failures of connectionist models of learning and memory. *Psychological Review*, 102, 419–457. https://doi.org/10.1037/0033-295X.102.3.419 — 〔理論〕
- [Kumaran2016] Kumaran, D., Hassabis, D., & McClelland, J. L. (2016). What learning systems do intelligent agents need? Complementary learning systems theory updated. *Trends in Cognitive Sciences*, 20, 512–534. https://doi.org/10.1016/j.tics.2016.05.004 — 〔総説〕〔理論〕
- [Tse2007] Tse, D., et al. (2007). Schemas and memory consolidation. *Science*, 316, 76–82. https://doi.org/10.1126/science.1135935 — 〔A-介入〕
- [Dusek1997] Dusek, J. A., & Eichenbaum, H. (1997). The hippocampus and memory for orderly stimulus relations. *Proceedings of the National Academy of Sciences*, 94, 7109–7114. https://doi.org/10.1073/pnas.94.13.7109 — 〔A-介入〕
- [Zeithamova2012] Zeithamova, D., Dominick, A. L., & Preston, A. R. (2012). Hippocampal and ventral medial prefrontal activation during retrieval-mediated learning supports novel inference. *Neuron*, 75, 168–179. https://doi.org/10.1016/j.neuron.2012.05.010 — 〔H-観察〕
- [Schapiro2017] Schapiro, A. C., Turk-Browne, N. B., Botvinick, M. M., & Norman, K. A. (2017). Complementary learning systems within the hippocampus: A neural network modelling approach to reconciling episodic memory with statistical learning. *Philosophical Transactions of the Royal Society B*, 372, 20160049. https://doi.org/10.1098/rstb.2016.0049 — 〔理論〕
- [Tolman1948] Tolman, E. C. (1948). Cognitive maps in rats and men. *Psychological Review*, 55, 189–208. https://doi.org/10.1037/h0061626 — 〔A-観察〕。ラットの行動実験の古典。脳への介入はない
- [Behrens2018] Behrens, T. E. J., et al. (2018). What is a cognitive map? Organizing knowledge for flexible behavior. *Neuron*, 100, 490–509. https://doi.org/10.1016/j.neuron.2018.10.002 — 〔総説〕
- [Stachenfeld2017] Stachenfeld, K. L., Botvinick, M. M., & Gershman, S. J. (2017). The hippocampus as a predictive map. *Nature Neuroscience*, 20, 1643–1653. https://doi.org/10.1038/nn.4650 — 〔理論〕

### 干渉・忘却

- [Murre2015] Murre, J. M. J., & Dros, J. (2015). Replication and analysis of Ebbinghaus' forgetting curve. *PLoS ONE*, 10, e0120644. https://doi.org/10.1371/journal.pone.0120644 — 〔H-観察〕
- [Anderson1994] Anderson, M. C., Bjork, R. A., & Bjork, E. L. (1994). Remembering can cause forgetting: Retrieval dynamics in long-term memory. *Journal of Experimental Psychology: Learning, Memory, and Cognition*, 20, 1063–1087. https://doi.org/10.1037/0278-7393.20.5.1063 — 〔H-観察〕
- [Shuai2010] Shuai, Y., et al. (2010). Forgetting is regulated through Rac activity in Drosophila. *Cell*, 140, 579–589. https://doi.org/10.1016/j.cell.2009.12.044 — 〔A-介入〕
- [Akers2014] Akers, K. G., et al. (2014). Hippocampal neurogenesis regulates forgetting during adulthood and infancy. *Science*, 344, 598–602. https://doi.org/10.1126/science.1248903 — 〔A-介入〕
- [HayashiTakagi2015] Hayashi-Takagi, A., et al. (2015). Labelling and optical erasure of synaptic memory traces in the motor cortex. *Nature*, 525, 333–338. https://doi.org/10.1038/nature15257 — 〔A-介入〕
- [Davis2017] Davis, R. L., & Zhong, Y. (2017). The biology of forgetting—A perspective. *Neuron*, 95, 490–503. https://doi.org/10.1016/j.neuron.2017.05.039 — 〔総説〕
- [Richards2017] Richards, B. A., & Frankland, P. W. (2017). The persistence and transience of memory. *Neuron*, 94, 1071–1084. https://doi.org/10.1016/j.neuron.2017.04.037 — 〔総説〕
- [McCloskey1989] McCloskey, M., & Cohen, N. J. (1989). Catastrophic interference in connectionist networks: The sequential learning problem. *Psychology of Learning and Motivation*, 24, 109–165. https://doi.org/10.1016/S0079-7421(08)60536-8 — 〔理論〕
- [Kirkpatrick2017] Kirkpatrick, J., et al. (2017). Overcoming catastrophic forgetting in neural networks. *Proceedings of the National Academy of Sciences*, 114, 3521–3526. https://doi.org/10.1073/pnas.1611835114 — 〔理論〕

### 記憶の利用

- [Pfeiffer2013] Pfeiffer, B. E., & Foster, D. J. (2013). Hippocampal place-cell sequences depict future paths to remembered goals. *Nature*, 497, 74–79. https://doi.org/10.1038/nature12112 — 〔A-観察〕
- [Jadhav2012] Jadhav, S. P., Kemere, C., German, P. W., & Frank, L. M. (2012). Awake hippocampal sharp-wave ripples support spatial memory. *Science*, 336, 1454–1458. https://doi.org/10.1126/science.1217230 — 〔A-介入〕
- [Gershman2017] Gershman, S. J., & Daw, N. D. (2017). Reinforcement learning and episodic memory in humans and animals: An integrative framework. *Annual Review of Psychology*, 68, 101–128. https://doi.org/10.1146/annurev-psych-122414-033625 — 〔総説〕
- [Funahashi1989] Funahashi, S., Bruce, C. J., & Goldman-Rakic, P. S. (1989). Mnemonic coding of visual space in the monkey's dorsolateral prefrontal cortex. *Journal of Neurophysiology*, 61, 331–349. https://doi.org/10.1152/jn.1989.61.2.331 — 〔A-観察〕。サル。遅延中の持続する発火
- [GoldmanRakic1995] Goldman-Rakic, P. S. (1995). Cellular basis of working memory. *Neuron*, 14, 477–485. https://doi.org/10.1016/0896-6273(95)90304-6 — 〔総説〕（持続する発火）
- [Mongillo2008] Mongillo, G., Barak, O., & Tsodyks, M. (2008). Synaptic theory of working memory. *Science*, 319, 1543–1546. https://doi.org/10.1126/science.1150769 — 〔理論〕
- [Stokes2015] Stokes, M. G. (2015). 'Activity-silent' working memory in prefrontal cortex: A dynamic coding framework. *Trends in Cognitive Sciences*, 19, 394–405. https://doi.org/10.1016/j.tics.2015.05.004 — 〔総説〕

### 人工のシステム（比較のため）

- [Graves2016] Graves, A., et al. (2016). Hybrid computing using a neural network with dynamic external memory. *Nature*, 538, 471–476. https://doi.org/10.1038/nature20101 — 外部の記憶を読み書きするネットワーク
- [Lewis2020] Lewis, P., et al. (2020). Retrieval-augmented generation for knowledge-intensive NLP tasks. *arXiv*:2005.11401. https://arxiv.org/abs/2005.11401 — 検索で補う言語モデル（RAG）
