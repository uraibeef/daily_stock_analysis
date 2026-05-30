import type React from 'react';
import { useMemo } from 'react';
import type { AnalysisReport, HistoryItem, StockHistoryFilters, StockHistoryRange } from '../../types/analysis';
import { getSentimentColor } from '../../types/analysis';
import { formatDateTime, formatReportType } from '../../utils/format';
import { Badge, Button, Drawer } from '../common';
import { DashboardStateBlock } from '../dashboard';

interface StockHistoryTrendDrawerProps {
  report: AnalysisReport;
  items: HistoryItem[];
  total: number;
  hasMore: boolean;
  isLoading: boolean;
  isLoadingMore: boolean;
  error?: unknown;
  filters: StockHistoryFilters;
  onClose: () => void;
  onRangeChange: (range: StockHistoryRange) => void;
  onLoadMore: () => void;
  onSelectRecord: (recordId: number) => void;
  onRetry: () => void;
}

const RANGE_OPTIONS: Array<{ value: StockHistoryRange; label: string }> = [
  { value: '30d', label: '近30天' },
  { value: '90d', label: '近90天' },
  { value: 'all', label: '全部' },
];

const isPresent = <T,>(value: T | null | undefined): value is T =>
  value !== undefined && value !== null && value !== '';

const formatNumber = (value?: number, digits = 2): string =>
  typeof value === 'number' && Number.isFinite(value) ? value.toFixed(digits) : '--';

const formatChangePct = (value?: number): string => {
  if (typeof value !== 'number' || !Number.isFinite(value)) {
    return '--';
  }
  const sign = value > 0 ? '+' : '';
  return `${sign}${value.toFixed(2)}%`;
};

const getPriceChangeStyle = (value?: number): React.CSSProperties | undefined => {
  if (typeof value !== 'number' || !Number.isFinite(value) || value === 0) {
    return undefined;
  }
  return { color: value > 0 ? 'var(--home-price-up)' : 'var(--home-price-down)' };
};

const formatAdvice = (item: Pick<HistoryItem, 'operationAdvice' | 'trendPrediction'>): string => {
  const advice = item.operationAdvice?.trim();
  const trend = item.trendPrediction?.trim();
  if (advice && trend) {
    return `${advice} / ${trend}`;
  }
  return advice || trend || '--';
};

const summarizeView = (items: HistoryItem[], currentId?: number) => {
  const scores = items
    .map((item) => item.sentimentScore)
    .filter((score): score is number => typeof score === 'number' && Number.isFinite(score));
  const current = items.find((item) => item.id === currentId) || items[0];
  const averageScore = scores.length
    ? scores.reduce((sum, score) => sum + score, 0) / scores.length
    : undefined;
  const scoreTrail = scores.slice(0, 8).reverse();
  const models = new Map<string, number>();
  items.forEach((item) => {
    const model = item.modelUsed?.trim() || '未记录';
    models.set(model, (models.get(model) || 0) + 1);
  });

  return {
    current,
    averageScore,
    scoreTrail,
    modelSummary: Array.from(models.entries())
      .sort((a, b) => b[1] - a[1])
      .slice(0, 3)
      .map(([model, count]) => `${model} ${count}次`)
      .join(' / '),
  };
};

const MetricItem: React.FC<{ label: string; value: React.ReactNode; title?: string }> = ({ label, value, title }) => (
  <div className="min-w-0 rounded-lg border border-border/60 bg-background/50 px-3 py-2">
    <p className="text-xs text-muted-text">{label}</p>
    <p className="mt-1 truncate text-sm font-semibold text-foreground" title={title}>
      {value}
    </p>
  </div>
);

export const StockHistoryTrendDrawer: React.FC<StockHistoryTrendDrawerProps> = ({
  report,
  items,
  total,
  hasMore,
  isLoading,
  isLoadingMore,
  error,
  filters,
  onClose,
  onRangeChange,
  onLoadMore,
  onSelectRecord,
  onRetry,
}) => {
  const currentRecordId = report.meta.id;
  const stockLabel = `${report.meta.stockName || report.meta.stockCode} ${report.meta.stockCode}`;
  const summary = useMemo(() => summarizeView(items, currentRecordId), [currentRecordId, items]);
  const currentItem = summary.current;
  const currentScore = currentItem?.sentimentScore ?? report.summary.sentimentScore;
  const currentModel = report.meta.modelUsed || currentItem?.modelUsed || '--';
  const currentAdvice = currentItem
    ? formatAdvice(currentItem)
    : formatAdvice({
        operationAdvice: report.summary.operationAdvice,
        trendPrediction: report.summary.trendPrediction,
      });

  return (
    <Drawer
      isOpen
      onClose={onClose}
      title="同股历史趋势"
      titleEyebrow="历史分析"
      width="max-w-2xl"
      zIndex={90}
      backdropClassName="bg-background/48 backdrop-blur-[2px]"
    >
      <div className="space-y-4">
        <section className="rounded-xl border border-border/70 bg-background/35 p-4">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="min-w-0">
              <h3 className="truncate text-lg font-semibold text-foreground">{stockLabel}</h3>
              <p className="mt-1 text-sm text-secondary-text">
                共 {total || items.length} 次分析 · 最近 {formatDateTime(items[0]?.createdAt || report.meta.createdAt)}
              </p>
            </div>
            <Badge variant="info" size="sm" className="shrink-0 shadow-none">
              当前 {currentAdvice}
            </Badge>
          </div>

          <div className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-4">
            <MetricItem label="当前分数" value={formatNumber(currentScore, 0)} />
            <MetricItem label="平均分" value={formatNumber(summary.averageScore, 1)} />
            <MetricItem label="当前价格" value={formatNumber(currentItem?.currentPrice, 2)} />
            <MetricItem label="当前模型" value={currentModel} title={currentModel} />
          </div>

          {summary.scoreTrail.length >= 2 ? (
            <div className="mt-4 rounded-lg border border-border/60 bg-card/50 px-3 py-2.5">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-xs text-secondary-text">评分变化</span>
                {summary.scoreTrail.map((score, index) => (
                  <span key={`${score}-${index}`} className="flex items-center gap-2">
                    {index > 0 && <span className="text-muted-text">→</span>}
                    <span
                      className="rounded-full border px-2 py-0.5 font-mono text-xs font-semibold"
                      style={{
                        color: getSentimentColor(score),
                        borderColor: `${getSentimentColor(score)}40`,
                        backgroundColor: `${getSentimentColor(score)}12`,
                      }}
                    >
                      {score}
                    </span>
                  </span>
                ))}
              </div>
              {summary.modelSummary ? (
                <p className="mt-2 truncate text-xs text-secondary-text" title={summary.modelSummary}>
                  模型记录：{summary.modelSummary}
                </p>
              ) : null}
            </div>
          ) : (
            <p className="mt-4 rounded-lg border border-dashed border-border/70 bg-card/45 px-3 py-2 text-sm text-secondary-text">
              当前历史记录不足，暂无法形成连续趋势。
            </p>
          )}
        </section>

        <section className="rounded-xl border border-border/70 bg-background/35 p-3">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex flex-wrap items-center gap-2">
              {RANGE_OPTIONS.map((option) => (
                <button
                  key={option.value}
                  type="button"
                  onClick={() => onRangeChange(option.value)}
                  className={`rounded-lg border px-3 py-1.5 text-xs font-medium transition-colors ${
                    filters.range === option.value
                      ? 'border-primary/50 bg-primary/10 text-primary'
                      : 'border-border/70 bg-card/55 text-secondary-text hover:bg-hover hover:text-foreground'
                  }`}
                >
                  {option.label}
                </button>
              ))}
            </div>
            <p className="text-xs text-secondary-text">按分析时间倒序</p>
          </div>
        </section>

        {isLoading ? (
          <DashboardStateBlock loading compact title="加载同股历史中..." />
        ) : error ? (
          <DashboardStateBlock
            compact
            title="历史趋势加载失败"
            description="请稍后重试"
            action={(
              <Button variant="secondary" size="sm" onClick={onRetry}>
                重新加载
              </Button>
            )}
          />
        ) : items.length === 0 ? (
          <DashboardStateBlock
            compact
            title="暂无更多同股历史分析"
            description="完成多次分析后，这里会展示观点变化、评分走势和模型记录。"
          />
        ) : (
          <section className="rounded-xl border border-border/70 bg-background/35">
            <div className="flex items-center justify-between border-b border-border/60 px-4 py-3">
              <h4 className="text-sm font-semibold text-foreground">历史记录</h4>
              <span className="text-xs text-secondary-text">
                已加载 {items.length} / {total || items.length} 条
              </span>
            </div>

            <div className="divide-y divide-border/55">
              {items.map((item) => {
                const isCurrent = item.id === currentRecordId;
                const sentimentColor = isPresent(item.sentimentScore)
                  ? getSentimentColor(item.sentimentScore)
                  : undefined;
                const scoreStyle = sentimentColor
                  ? {
                      color: sentimentColor,
                      borderColor: `${sentimentColor}40`,
                      backgroundColor: `${sentimentColor}12`,
                    }
                  : undefined;

                return (
                  <button
                    key={item.id}
                    type="button"
                    onClick={() => onSelectRecord(item.id)}
                    className={`grid w-full grid-cols-1 gap-3 px-4 py-3 text-left transition-colors sm:grid-cols-[8.5rem_minmax(0,1fr)_7.5rem] ${
                      isCurrent ? 'bg-primary/8' : 'hover:bg-hover/55'
                    }`}
                  >
                    <div className="space-y-1">
                      <p className="font-mono text-xs text-secondary-text">{formatDateTime(item.createdAt)}</p>
                      <div className="flex flex-wrap gap-1.5">
                        {isCurrent ? (
                          <Badge variant="info" size="sm" className="shadow-none">
                            当前
                          </Badge>
                        ) : null}
                        {item.reportType ? (
                          <Badge variant="default" size="sm" className="shadow-none">
                            {formatReportType(item.reportType)}
                          </Badge>
                        ) : null}
                      </div>
                    </div>

                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="text-sm font-semibold text-foreground">{formatAdvice(item)}</span>
                        {isPresent(item.sentimentScore) ? (
                          <span
                            className="rounded-full border px-2 py-0.5 font-mono text-xs font-semibold"
                            style={scoreStyle}
                          >
                            {item.sentimentScore}
                          </span>
                        ) : null}
                        <span
                          className="font-mono text-xs text-secondary-text"
                          style={getPriceChangeStyle(item.changePct)}
                        >
                          {formatChangePct(item.changePct)}
                        </span>
                      </div>
                      <p className="mt-1 line-clamp-2 text-sm leading-6 text-secondary-text">
                        {item.analysisSummary || '暂无分析摘要'}
                      </p>
                    </div>

                    <div className="min-w-0 text-left sm:text-right">
                      <p className="truncate text-xs text-secondary-text" title={item.modelUsed || '未记录模型'}>
                        {item.modelUsed || '未记录模型'}
                      </p>
                      <p className="mt-1 font-mono text-xs text-secondary-text">
                        价格 {formatNumber(item.currentPrice, 2)}
                      </p>
                    </div>
                  </button>
                );
              })}
            </div>

            {hasMore ? (
              <div className="flex justify-center border-t border-border/60 px-4 py-3">
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={onLoadMore}
                  isLoading={isLoadingMore}
                  loadingText="加载中..."
                >
                  加载更多
                </Button>
              </div>
            ) : null}
          </section>
        )}
      </div>
    </Drawer>
  );
};
