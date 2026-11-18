export default function ErrorBanner({ message, onReload }: { message: string | null; onReload?: () => void }) {
  if (!message) return null;
  return (
    <div className="banner error" role="alert">
      <span>{message}</span>
      {onReload && <button type="button" onClick={onReload}>Muat ulang</button>}
    </div>
  );
}
