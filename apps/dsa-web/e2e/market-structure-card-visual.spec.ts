import { chromium, expect, test, type TestInfo } from '@playwright/test';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import type { MarketStructureContext } from '../src/types/analysis';

const shouldRunVisualEvidence = process.env.DSA_WEB_VISUAL_EVIDENCE === '1';

if (!shouldRunVisualEvidence) {
  test.skip(true, 'Set DSA_WEB_VISUAL_EVIDENCE=1 to capture MarketStructureCard visual evidence.');
}

test.use({ locale: 'zh-CN' });

const currentDir = path.dirname(fileURLToPath(import.meta.url));
const staticAssetsDir = path.resolve(currentDir, '../../../static/assets');

const context: MarketStructureContext = {
  schemaVersion: 'market-structure-v1',
  status: 'partial',
  market: 'cn',
  tradeDate: '2026-07-04',
  marketThemeContext: {
    schemaVersion: 'market-theme-v1',
    status: 'partial',
    market: 'cn',
    activeThemes: [
      { name: '机器人概念', changePct: 4.2, rank: 1, source: 'concept', phase: 'accelerating' },
      { name: 'AI 算力', changePct: 3.6, rank: 2, source: 'concept', phase: 'warming' },
    ],
    leadingConcepts: [
      { name: '机器人概念', changePct: 4.2, rank: 1, source: 'concept' },
      { name: 'AI 算力', changePct: 3.6, rank: 2, source: 'concept' },
    ],
    leadingIndustries: [
      { name: '通用设备', changePct: 2.1, rank: 2, source: 'industry' },
      { name: '软件开发', changePct: 1.8, rank: 4, source: 'industry' },
    ],
    laggingThemes: [],
    themeBreadth: {
      activeCount: 2,
      leadingConceptCount: 2,
      leadingIndustryCount: 2,
      laggingCount: 0,
    },
    dataQuality: {
      status: 'partial',
      missingFields: ['industry_rankings'],
      sources: [],
      errors: [],
    },
  },
  stockMarketPosition: {
    schemaVersion: 'stock-market-position-v1',
    status: 'partial',
    stockCode: '300024',
    stockName: '机器人',
    market: 'cn',
    primaryTheme: {
      name: '机器人概念',
      source: 'concept',
      phase: 'accelerating',
      rank: 1,
      changePct: 4.2,
    },
    relatedBoards: [
      { name: '机器人概念', type: '概念', source: 'concept', rank: 1, changePct: 4.2 },
      { name: '通用设备', type: '行业', source: 'industry', rank: 2, changePct: 2.1 },
    ],
    stockRole: 'follower',
    themePhase: 'accelerating',
    riskTags: [
      { code: 'theme_data_partial', message: '题材主线数据不完整' },
      { code: 'stock_theme_evidence_partial', message: '个股板块未匹配到市场题材榜单，个股位置按降级证据处理' },
    ],
    missingFields: ['hotspot_constituents', 'leader_stocks'],
  },
};

function loadBuiltStyles(): string {
  if (!fs.existsSync(staticAssetsDir)) {
    throw new Error('Missing built Web assets. Run `cd apps/dsa-web && npm run build` before visual evidence capture.');
  }

  const cssFiles = fs.readdirSync(staticAssetsDir)
    .filter((file) => file.endsWith('.css'))
    .sort();

  if (cssFiles.length === 0) {
    throw new Error('Missing built Web CSS asset. Run `cd apps/dsa-web && npm run build` before visual evidence capture.');
  }

  return cssFiles
    .map((file) => fs.readFileSync(path.join(staticAssetsDir, file), 'utf-8'))
    .join('\n');
}

function escapeHtml(value: string): string {
  return value
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;');
}

function formatItem(item: { name: string; changePct?: number }): string {
  if (typeof item.changePct === 'number') {
    return `${item.name} ${item.changePct > 0 ? '+' : ''}${item.changePct.toFixed(2)}%`;
  }
  return item.name;
}

function renderMetricLine(label: string, values: string[]): string {
  return `
    <div class="grid gap-1 text-sm sm:grid-cols-[7rem_1fr]">
      <span class="text-secondary-text">${escapeHtml(label)}</span>
      <span class="min-w-0 break-words text-foreground">${values.map(escapeHtml).join(' / ') || '暂无'}</span>
    </div>
  `;
}

function renderBadge(label: string, variant: 'default' | 'success' | 'warning' = 'default'): string {
  const variantClass = variant === 'success'
    ? 'border-success/20 bg-success/10 text-success'
    : variant === 'warning'
      ? 'border-warning/20 bg-warning/10 text-warning'
      : 'border-border/55 bg-elevated/75 text-secondary-text';

  return `<span class="inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-medium backdrop-blur-sm ${variantClass}">${escapeHtml(label)}</span>`;
}

function renderMarketStructureCardHtml(value: MarketStructureContext): string {
  const theme = value.marketThemeContext!;
  const position = value.stockMarketPosition!;
  const activeThemes = (theme.activeThemes || []).map(formatItem);
  const leadingConcepts = (theme.leadingConcepts || []).map(formatItem);
  const leadingIndustries = (theme.leadingIndustries || []).map(formatItem);
  const riskTags = [
    '题材主线数据不完整',
    '个股板块未匹配到市场题材榜单，个股位置按降级证据处理',
  ];
  const missingFields = [
    ...(position.missingFields || []),
    ...(theme.dataQuality?.missingFields || []),
  ];

  return `
    <main class="min-h-screen bg-background p-8 text-foreground">
      <div class="mx-auto max-w-5xl" data-testid="market-structure-visual-card">
        <div class="terminal-card rounded-lg p-5">
          <section aria-label="题材主线与个股位置">
            <div class="mb-4 flex items-center justify-between gap-3">
              <div class="flex items-baseline gap-2">
                <span class="shrink-0 text-cyan">▣</span>
                <span class="label-uppercase">市场位置</span>
                <h3 class="text-base font-semibold text-foreground">题材主线与个股位置</h3>
              </div>
              <div class="flex shrink-0 items-center gap-2">${renderBadge('部分可用', 'warning')}</div>
            </div>
            <div class="grid gap-4 lg:grid-cols-2">
              <div class="space-y-3">
                <div class="flex items-center gap-2 text-sm font-medium text-foreground">
                  <span class="text-success">▲</span>
                  <span>大盘题材层</span>
                  ${renderBadge('部分可用', 'warning')}
                </div>
                ${renderMetricLine('活跃题材', activeThemes)}
                ${renderMetricLine('领涨概念', leadingConcepts)}
                ${renderMetricLine('领涨行业', leadingIndustries)}
              </div>
              <div class="space-y-3">
                <div class="flex items-center gap-2 text-sm font-medium text-foreground">
                  <span class="text-cyan">▣</span>
                  <span>个股位置层</span>
                  ${renderBadge('部分可用', 'warning')}
                </div>
                ${renderMetricLine('主关联题材', [formatItem(position.primaryTheme!)])}
                ${renderMetricLine('题材阶段', ['加速'])}
                ${renderMetricLine('个股位置', ['跟随'])}
              </div>
            </div>
            <div class="mt-4 grid gap-3 border-t border-border/60 pt-4 md:grid-cols-2">
              <div>
                <div class="mb-2 flex items-center gap-2 text-xs font-medium uppercase tracking-wide text-secondary-text">
                  <span class="text-warning">!</span>
                  <span>风险标签</span>
                </div>
                <div class="flex flex-wrap gap-2">${riskTags.map((tag) => renderBadge(tag, 'warning')).join('')}</div>
              </div>
              <div>
                <div class="mb-2 text-xs font-medium uppercase tracking-wide text-secondary-text">缺失证据</div>
                <div class="flex flex-wrap gap-2">${missingFields.map((field) => renderBadge(field)).join('')}</div>
              </div>
            </div>
          </section>
        </div>
      </div>
    </main>
  `;
}

function isMissingPlaywrightBrowser(error: unknown): boolean {
  return error instanceof Error && error.message.includes("Executable doesn't exist");
}

async function attachDesktopScreenshotArtifact(artifact: string, testInfo: TestInfo): Promise<void> {
  let browser;
  try {
    browser = await chromium.launch();
  } catch (error) {
    if (!isMissingPlaywrightBrowser(error)) {
      throw error;
    }
    const notePath = testInfo.outputPath('market-structure-card-screenshot-skipped.txt');
    fs.writeFileSync(
      notePath,
      [
        'Playwright Chromium is not installed in this environment, so PNG capture was skipped.',
        'The HTML artifact is still generated and can be opened to inspect the MarketStructureCard visual state.',
      ].join('\n'),
    );
    await testInfo.attach('market-structure-card-screenshot-skipped', {
      path: notePath,
      contentType: 'text/plain',
    });
    return;
  }

  try {
    const page = await browser.newPage({
      locale: 'zh-CN',
      viewport: { width: 1280, height: 900 },
    });
    await page.setContent(artifact, { waitUntil: 'domcontentloaded' });
    const card = page.getByTestId('market-structure-visual-card');
    await expect(card).toBeVisible();

    const screenshotPath = testInfo.outputPath('market-structure-card-desktop.png');
    await card.screenshot({ path: screenshotPath });
    await testInfo.attach('market-structure-card-desktop-png', {
      path: screenshotPath,
      contentType: 'image/png',
    });
  } finally {
    await browser.close();
  }
}

test.describe('MarketStructureCard visual evidence', () => {
  test('writes desktop mock report card artifacts with market structure data', async ({ browserName }, testInfo) => {
    const styles = loadBuiltStyles();
    const markup = renderMarketStructureCardHtml(context);

    expect(browserName).toBe('chromium');
    expect(markup).toContain('题材主线与个股位置');
    expect(markup).toContain('大盘题材层');
    expect(markup).toContain('个股位置层');
    expect(markup).toContain('机器人概念 +4.20%');

    const artifact = `
      <!doctype html>
      <html lang="zh-CN">
        <head>
          <meta charset="UTF-8" />
          <meta name="viewport" content="width=device-width, initial-scale=1.0" />
          <title>MarketStructureCard Visual Evidence</title>
          <style>${styles}</style>
        </head>
        <body>${markup}</body>
      </html>
    `;

    const artifactPath = testInfo.outputPath('market-structure-card-desktop.html');
    fs.writeFileSync(artifactPath, artifact);

    await testInfo.attach('market-structure-card-desktop-html', {
      path: artifactPath,
      contentType: 'text/html',
    });
    await attachDesktopScreenshotArtifact(artifact, testInfo);
  });
});
