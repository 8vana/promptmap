# STATUS — promptmap

_最終更新: 2026-06-08 (このセッション)_

> 注: このセッションは `/wrap` のみで、コード変更は行っていない。本ファイルは
> リポジトリ状態と git ログから初期化したスナップショット。次回以降のセッションが
> 実作業を反映して更新していく。

## 現在地（今どのマイルストーン上か）
JBF-FORGE（paper→attack 自動足場化ワークフロー）が production まで到達済み（PR #46 マージ）。
次フェーズは `docs/forge_strengthening_design.md` の「Forge Strengthening」= 生成コードの
汎用ベースライン依存を減らし、plan ステップを直接実装するドラフトを作ること。

## 進捗（マイルストーン / フェーズの達成状況）
- ✅ PromptMap ランタイム基盤（`BaseAttack` / `AttackContext` / 攻撃レジストリ / ベンチマーク）
- ✅ 既存攻撃群（Single PI / Crescendo / PAIR / TAP / Chunked / Attack Agent）
- ✅ `paper_attack_scaffold` ベースの staging オンボーディング
- ✅ JBF-FORGE Phase A: Planner（paper→implementation plan）
- ✅ JBF-FORGE Phase B: Forger/Coder（heuristic / auto / llm バックエンド、テンプレ複数）
- ✅ JBF-FORGE Phase C: Auditor（plan→code カバレッジ検証）
- ✅ JBF-FORGE production: Verifier / Promoter / lifecycle / status / quality 一式（PR #46）
- ✅ 攻撃シグネチャの日本語化（PR #41）
- 🟡 Forge Strengthening（`docs/forge_strengthening_design.md`、Status は "Proposed" のまま未着手）
  - ⏳ 生成 `attack_module.py` の汎用フロー脱却（plan ステップの直接実装）
  - ⏳ audit が検証しやすい coder 出力構造
  - ⏳ 不確実性を隠さず明示する出力

## 直近やったこと（最大3件）
- JBF-FORGE production 実装をマージ（PR #46 / 28cbe92）— Verifier・Promoter・lifecycle・status・quality 追加、radial_e2e を staging へ整理
- JBF-FORGE 本体実装の完了（PR #45）
- Forge の強化（enhanced forge, PR #44）

## Next Action（次の一手・実行可能な粒度で1つ）
- `docs/forge_strengthening_design.md` の「1. Runtime Logic Is Too Generic」に着手する。
  まず `tools/paper_attack_scaffold/forger.py` の llm バックエンド経路で、抽出済み plan の
  algorithm steps を `templates/attack_module_forge.py.j2` の本体ロジックに 1:1 で展開する
  プロンプト／テンプレ変更を入れ、`tests/test_paper_attack_scaffold.py` に
  「plan ステップ数 ≒ 生成モジュール内の対応処理数」を確認するアサーションを追加する。

## ブロッカー / 未決事項
- なし（Forge Strengthening は設計 doc 済み・実装待ちのみ）

## メモ（再構築コストの高い判断の理由）
- 作業対象リポジトリは **promptmap**。`/home/itakaesu/CLAUDE.md` は別プロジェクト
  「AgenticMap」の指示であり、このリポジトリの内容（promptmap）とは一致しない点に注意。
- JBF-FORGE は JBF（Jailbreak Foundry）の完全再現ではなく、PromptMap ネイティブな
  軽量 paper→attack ワークフローとして意図的にスコープを絞っている
  （`BaseAttack`/`AttackContext` は不変、promotion は人間レビュー前提、ランタイム外）。
