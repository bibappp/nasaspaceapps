import { MessageCircle } from "lucide-react";
import { QRCodeSVG } from "qrcode.react";
import { useTranslation } from "react-i18next";

const botUrl = () => (import.meta.env.VITE_TELEGRAM_BOT_URL ?? "").trim();

export default function TelegramBotCard({ className = "" }: { className?: string }) {
  const { t } = useTranslation();
  const url = botUrl();
  if (!url) return null;

  return (
    <div
      className={`flex flex-col gap-4 rounded-lg border border-line bg-white p-4 sm:flex-row sm:items-center sm:gap-6 sm:p-5 ${className}`}
    >
      <MessageCircle className="hidden h-9 w-9 flex-none text-sky-600 sm:block" aria-hidden />
      <div className="min-w-0 flex-1">
        <h2 className="text-base font-semibold text-ink">{t("telegram.title")}</h2>
        <p className="mt-1 text-sm leading-relaxed text-ink-muted">{t("telegram.text")}</p>
        <a
          href={url}
          target="_blank"
          rel="noopener noreferrer"
          className="btn-primary mt-3 inline-flex h-9 no-underline"
        >
          <MessageCircle className="h-4 w-4" aria-hidden />
          {t("telegram.open_bot")}
        </a>
      </div>
      <div
        className="flex shrink-0 items-center justify-center self-center rounded-md border border-line bg-white p-2"
        role="img"
        aria-label={t("telegram.qr_alt")}
      >
        <QRCodeSVG value={url} size={88} level="M" marginSize={0} title={t("telegram.qr_alt")} />
      </div>
    </div>
  );
}