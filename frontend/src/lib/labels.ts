import type {
  CardStatus,
  CardType,
  GapStatus,
  HandoverReason,
  ProcessFrequency,
  RecordingStage,
  RecordingStatus,
  Verification,
} from "@/api/client";

export const REASON_LABELS: Record<HandoverReason, string> = {
  retirement: "Выход на пенсию",
  leave: "Декретный отпуск",
  resignation: "Увольнение",
  transfer: "Перевод",
  other: "Другое",
};

export const FREQUENCY_LABELS: Record<ProcessFrequency, string> = {
  daily: "Ежедневно",
  weekly: "Еженедельно",
  monthly: "Ежемесячно",
  quarterly: "Раз в квартал / семестр",
  yearly: "Раз в год",
  adhoc: "По необходимости",
};

export const CRITICALITY_LABELS: Record<number, string> = {
  1: "Низкая",
  2: "Средняя",
  3: "Высокая",
};

export const CARD_TYPE_LABELS: Record<CardType, string> = {
  procedure: "Инструкция",
  rule: "Правило / признак",
  exception: "Исключение",
  pitfall: "Типичная ошибка",
  contact: "К кому обращаться",
  deadline: "Сроки",
  term: "Термин",
};

export const CARD_STATUS_LABELS: Record<CardStatus, string> = {
  draft: "Черновик",
  approved: "Подтверждена",
  rejected: "Отклонена",
  archived: "В архиве",
};

/** «через 5 дней», «сегодня», «просрочено на 2 дня». */
export function daysLeft(deadline: string | null | undefined, today = new Date()): string | null {
  if (!deadline) return null;
  const start = Date.UTC(today.getFullYear(), today.getMonth(), today.getDate());
  const [y, m, d] = deadline.split("-").map(Number);
  const days = Math.round((Date.UTC(y, m - 1, d) - start) / 86_400_000);
  if (days === 0) return "сегодня";
  if (days < 0) return `просрочено на ${plural(-days, "день", "дня", "дней")}`;
  return `через ${plural(days, "день", "дня", "дней")}`;
}

export function plural(n: number, one: string, few: string, many: string): string {
  const mod10 = n % 10;
  const mod100 = n % 100;
  const word =
    mod10 === 1 && mod100 !== 11
      ? one
      : mod10 >= 2 && mod10 <= 4 && (mod100 < 10 || mod100 >= 20)
        ? few
        : many;
  return `${n} ${word}`;
}

export function formatMinutes(seconds: number): string {
  return plural(Math.round(seconds / 60), "минута", "минуты", "минут");
}

export const GAP_STATUS_LABELS: Record<GapStatus, string> = {
  open: "Ждёт ответа",
  answered: "Есть ответ",
  dismissed: "Закрыт без ответа",
};

/** The note under an answer (SPEC 7.8). */
export const VERIFICATION_NOTES: Record<Verification, string | null> = {
  verified: "Все утверждения подтверждены источниками",
  partially_removed: "Часть ответа удалена: не нашлось подтверждения",
  not_verified: "Ответ не удалось проверить — сверьтесь с источниками",
  degraded: null, // the answer itself says that the model is unavailable
  none: null,
};

export const RECORDING_STATUS_LABELS: Record<RecordingStatus, string> = {
  uploaded: "В очереди на обработку",
  processing: "Обрабатывается",
  ready: "Готова",
  failed: "Не обработана",
};

/** What the worker is doing (the page shows it instead of a progress bar, D-060). */
export const RECORDING_STAGE_LABELS: Record<RecordingStage, string> = {
  audio: "Извлекаю звук",
  speech: "Распознаю речь",
  steps: "Выделяю шаги",
  screenshots: "Готовлю скриншоты и скрываю персональные данные",
};

/** 75 000 → «01:15». */
export function timecode(ms: number): string {
  const seconds = Math.floor(ms / 1000);
  return `${String(Math.floor(seconds / 60)).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}`;
}
