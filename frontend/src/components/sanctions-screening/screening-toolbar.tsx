import type { SanctionsList, ScreeningEntityType } from "@/types/sanctions";

export type ScreeningMode = "standard" | "exact" | "enhanced";

export function ScreeningToolbar({ query, entityType, sanctionsList, mode, loading, onQueryChange, onEntityTypeChange, onSanctionsListChange, onModeChange, onScreen }: {
  query: string;
  entityType: "all" | ScreeningEntityType;
  sanctionsList: "all" | SanctionsList;
  mode: ScreeningMode;
  loading: boolean;
  onQueryChange: (value: string) => void;
  onEntityTypeChange: (value: "all" | ScreeningEntityType) => void;
  onSanctionsListChange: (value: "all" | SanctionsList) => void;
  onModeChange: (value: ScreeningMode) => void;
  onScreen: () => void;
}) {
  return (
    <form className="screening-toolbar" onSubmit={event => { event.preventDefault(); onScreen(); }}>
      <label className="screening-search"><span className="sr-only">搜索主体、船舶或所有人</span><i aria-hidden="true">⌕</i><input value={query} onChange={event => onQueryChange(event.target.value)} placeholder="搜索主体、船舶、所有人…" /></label>
      <label><span>主体类型</span><select value={entityType} onChange={event => onEntityTypeChange(event.target.value as "all" | ScreeningEntityType)}><option value="all">全部主体</option><option value="company">公司</option><option value="supplier">供应商</option><option value="shipowner">船东</option><option value="vessel">船舶</option><option value="individual">个人</option><option value="other">其他</option></select></label>
      <label><span>制裁名单</span><select value={sanctionsList} onChange={event => onSanctionsListChange(event.target.value as "all" | SanctionsList)}><option value="all">全部名单</option><option value="OFAC">OFAC</option><option value="UK">英国</option><option value="EU">欧盟</option><option value="UN">联合国</option></select></label>
      <label><span>筛查模式</span><select value={mode} onChange={event => onModeChange(event.target.value as ScreeningMode)}><option value="standard">标准</option><option value="exact">名称精确匹配</option><option value="enhanced">增强</option></select></label>
      <button className="screening-run-button" type="submit" disabled={loading || !query.trim()}>{loading ? "筛查中…" : "执行筛查"}</button>
      <button className="screening-batch-button" type="button" aria-disabled="true" title="批量上传功能将在后续版本开放">批量筛查</button>
    </form>
  );
}
