# MMM 数式全体像

## 表記

| 記号 | 意味 |
|:---|:---|
| $t = 1, \ldots, T$ | 時点（週 or 日） |
| $y_t$ | 実績CV（目的変数） |
| $x_{c,t}$ | チャネル $c$ のメディア信号（クリック or スペンド） |
| $s_{c,t}$ | チャネル $c$ のスペンド（費用） |
| $z_{k,t}$ | コントロール変数 $k$（気温・SEO等） |

---

## Step 1: 前処理（Sqrt変換）

CVの分布を正規化。

$$\tilde{y}_t = \sqrt{y_t}$$

---

## Step 2: Adstock変換（広告残存効果）

昨日の広告効果が今日に $\lambda$ 割残る、という幾何減衰。

$$A_{c,t} = x_{c,t} + \lambda_c \cdot A_{c,t-1} = \sum_{\tau=0}^{t-1} \lambda_c^{\tau} \cdot x_{c,t-\tau}$$

- $\lambda_c \in [0, 1]$：減衰率（carryover rate）
- $\lambda = 0$ → 即日消滅、$\lambda = 0.9$ → 効果が長く残る

---

## Step 3: Hill変換（飽和・S字曲線）

広告投資の限界収益逓減を表現。

$$H_{c,t} = \frac{A_{c,t}^{\alpha_c}}{A_{c,t}^{\alpha_c} + \gamma_c^{\alpha_c}}$$

- $\alpha_c > 0$：カーブの急峻さ（shape）。$\alpha > 1$ でS字、$0 < \alpha < 1$ で凹型
- $\gamma_c > 0$：変曲点（$H = 0.5$ になるAdstock量）

$$H_{c,t} \in (0, 1) \quad \text{（飽和すると1に漸近）}$$

---

## Step 4: 線形回帰モデル（本体）

$$\tilde{y}_t = \underbrace{\beta_0}_{\text{ベースライン}} + \underbrace{\sum_{c=1}^{C} \beta_c \cdot H_{c,t}}_{\text{媒体貢献}} + \underbrace{\sum_{k=1}^{K} \delta_k \cdot z_{k,t}}_{\text{コントロール変数}} + \epsilon_t$$

- $\beta_c \geq 0$（非負制約：広告がCVを減らすことはない）
- $\epsilon_t \sim \mathcal{N}(0, \sigma^2)$

推定はBayesian Ridge（L2正則化）：

$$\mathcal{L}(\boldsymbol{\beta}) = \|\tilde{\mathbf{y}} - \mathbf{X}\boldsymbol{\beta}\|^2 + \alpha_{\text{ridge}} \|\boldsymbol{\beta}\|^2$$

---

## Step 5: パラメータ推定（2段階）

Adstock・HillのパラメータとBayesian Ridgeの回帰係数は分けて最適化する。

```
全パラメータ θ = {λ_c, α_c, γ_c} × C チャネル分

① パレート探索（デフォルト2000試行）
   各 θ をランダムサンプリング → X を計算 → Bayesian Ridge で β を推定
   目的関数: min NRMSE × (1 - w) + RSSD × w   ← Robyn準拠

② L-BFGS-B 局所最適化
   ①のベスト解を初期値として勾配法でチューニング
```

---

## Step 6: 評価指標

$$R^2 = 1 - \frac{\sum_t (\tilde{y}_t - \hat{\tilde{y}}_t)^2}{\sum_t (\tilde{y}_t - \bar{\tilde{y}})^2}$$

→ 「売上変動の何%をモデルで説明できているか」として表示する。

$$\text{NRMSE} = \frac{\sqrt{\frac{1}{T}\sum_t (\tilde{y}_t - \hat{\tilde{y}}_t)^2}}{\max(\tilde{y}) - \min(\tilde{y})}$$

→ 予測精度。目安は train < 0.10、holdout < 0.15。

$$\text{RSSD} = \sqrt{\frac{1}{C}\sum_c \left( \frac{\hat{\beta}_c \sum_t H_{c,t}}{\sum_{c'}\hat{\beta}_{c'} \sum_t H_{c',t}} - \frac{\sum_t s_{c,t}}{\sum_{c'}\sum_t s_{c',t}} \right)^2}$$

→ CVの媒体帰属比率とスペンド比率の整合性。0.10〜0.25が適正範囲。

---

## Step 7: 予算最適化

$$\max_{\{b_c\}} \sum_{c=1}^{C} \hat{\beta}_c \cdot H_c(b_c;\, \hat{\alpha}_c, \hat{\gamma}_c)$$

$$\text{s.t.} \quad \sum_c b_c = B, \quad 0.5 \cdot s_c^{\text{実績}} \leq b_c \leq 2.0 \cdot s_c^{\text{実績}}$$

scipy の制約付き非線形最適化（SLSQP）で解く。

---

## 全体パイプライン（直感的まとめ）

```
生データ
  → √変換（外れ値を穏やかに）
    → Adstock（広告の残り香を積み上げ）
      → Hill（飽和させて0〜1に収める）
        → 線形回帰（βを当てはめてCVを予測）
          → Pareto探索で λ/α/γ を最適化
            → 予算最適化で次の一手を出す
```
