export type SectionTone = "primary" | "rose" | "violet";

const SECTION_TITLE_CLASS: Record<SectionTone, string> = {
  primary: "text-primary/70",
  rose: "text-rose-600/80 dark:text-rose-400/80",
  violet: "text-violet-600/80 dark:text-violet-300/80",
};

export function getSectionTitleClass(title: unknown, tone: SectionTone): string {
  if (tone === "rose" && title === "信号") {
    return SECTION_TITLE_CLASS.primary;
  }
  return SECTION_TITLE_CLASS[tone];
}
