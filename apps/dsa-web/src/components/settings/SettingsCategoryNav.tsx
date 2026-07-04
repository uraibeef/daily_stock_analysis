import type React from 'react';
import { Bell, Bot, Database, Layers3, LineChart, Settings2, SlidersHorizontal } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import { Badge } from '../common';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { getCategoryTitle } from '../../utils/systemConfigI18n';
import type { SystemConfigCategory, SystemConfigCategorySchema, SystemConfigItem } from '../../types/systemConfig';
import { cn } from '../../utils/cn';

interface SettingsCategoryNavProps {
  categories: SystemConfigCategorySchema[];
  itemsByCategory: Record<string, SystemConfigItem[]>;
  activeCategory: string;
  onSelect: (category: string) => void;
}

const categoryIconMap: Partial<Record<SystemConfigCategory, LucideIcon>> = {
  system: Settings2,
  base: SlidersHorizontal,
  data_source: Database,
  ai_model: Layers3,
  notification: Bell,
  agent: Bot,
  backtest: LineChart,
};

export const SettingsCategoryNav: React.FC<SettingsCategoryNavProps> = ({
  categories,
  itemsByCategory,
  activeCategory,
  onSelect,
}) => {
  const { language, t } = useUiLanguage();

  return (
    <nav
      className="h-full rounded-lg border settings-border bg-card/90 p-2 shadow-soft-card backdrop-blur-sm"
      aria-label={t('settings.categoryNavTitle')}
    >
      <div className="flex gap-2 overflow-x-auto pb-1 lg:block lg:space-y-1.5 lg:overflow-visible lg:pb-0">
        {categories.map((category) => {
          const isActive = category.category === activeCategory;
          const count = (itemsByCategory[category.category] || []).length;
          const title = getCategoryTitle(category.category, category.title, language);
          const Icon = categoryIconMap[category.category] ?? Layers3;

          return (
            <button
              key={category.category}
              type="button"
              className={cn(
                'flex min-w-[9rem] items-center gap-2 rounded-md border px-3 py-2.5 text-left transition-[background-color,border-color,box-shadow] duration-200 lg:min-w-0 lg:w-full',
                isActive
                  ? 'settings-nav-item-active'
                  : 'border-transparent bg-transparent hover:border-[var(--settings-border)] hover:bg-[var(--settings-surface-hover)]',
              )}
              onClick={() => onSelect(category.category)}
              aria-current={isActive ? 'page' : undefined}
            >
              <Icon
                className={cn('h-4 w-4 shrink-0', isActive ? 'text-[hsl(var(--primary))]' : 'text-muted-text')}
                aria-hidden="true"
              />
              <span className={cn('min-w-0 flex-1 truncate text-sm font-medium', isActive ? 'text-foreground' : 'text-secondary-text')}>
                {title}
              </span>
              <Badge
                variant={isActive ? 'info' : 'default'}
                size="sm"
                className={cn(
                  'shrink-0 px-1.5 py-0 text-[11px]',
                  isActive
                    ? 'settings-accent-badge border-[hsl(var(--primary)/0.32)]'
                    : 'border-[var(--settings-border)] bg-[var(--settings-surface)] text-muted-text',
                )}
              >
                {count}
              </Badge>
            </button>
          );
        })}
      </div>
    </nav>
  );
};
