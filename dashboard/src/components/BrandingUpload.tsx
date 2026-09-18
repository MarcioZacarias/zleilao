import { useRef, useState } from "react";
import { Upload, Loader2, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { brandingApi, BrandingKey } from "../services/settings";
import { errorMessage } from "../services/api";
import { refreshBranding } from "../hooks/useBranding";
import { Card, CardContent, CardHeader } from "./ui/Card";
import { Button } from "./ui/Button";

interface BrandingItem {
  key: BrandingKey;
  label: string;
  description: string;
  previewBg: string;
}

const ITEMS: BrandingItem[] = [
  {
    key: "logo_dark",
    label: "Logo (fundo escuro)",
    description: "Usado no portal público (header/footer), no login e no menu lateral do admin.",
    previewBg: "#0b1020",
  },
  {
    key: "logo_light",
    label: "Logo (fundo claro)",
    description: "Reservado para fundos claros (e-mails, PDFs futuros).",
    previewBg: "#ffffff",
  },
  {
    key: "favicon",
    label: "Favicon",
    description: "Ícone do navegador. SVG, PNG ou ICO, idealmente quadrado (32×32 ou 64×64).",
    previewBg: "#ffffff",
  },
];

function UploadCard({ item }: { item: BrandingItem }) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);
  const [previewUrl, setPreviewUrl] = useState<string>(brandingApi.url(item.key));
  const [hasAsset, setHasAsset] = useState(true);

  const handleFile = async (file: File) => {
    if (file.size > 2 * 1024 * 1024) {
      toast.error("Arquivo muito grande. Máximo 2 MB.");
      return;
    }
    setUploading(true);
    try {
      const data = await brandingApi.upload(item.key, file);
      toast.success(`${item.label} atualizado`);
      setPreviewUrl(data.url);
      setHasAsset(true);
      await refreshBranding();
    } catch (err) {
      toast.error(errorMessage(err, "Falha no upload"));
    }
    setUploading(false);
  };

  const handleDelete = async () => {
    if (!confirm(`Remover ${item.label}? O sistema voltará a usar o asset padrão.`)) return;
    setUploading(true);
    try {
      await brandingApi.remove(item.key);
      toast.success(`${item.label} removido. Usando padrão.`);
      setHasAsset(false);
      await refreshBranding();
    } catch (err) {
      toast.error(errorMessage(err, "Falha ao remover"));
    }
    setUploading(false);
  };

  return (
    <Card>
      <CardHeader>
        <h3 className="font-semibold text-gray-900">{item.label}</h3>
        <p className="mt-1 text-xs text-gray-500">{item.description}</p>
      </CardHeader>
      <CardContent>
        <div className="space-y-3">
          <div
            className="flex min-h-[120px] items-center justify-center rounded-lg border border-gray-200 p-4"
            style={{ backgroundColor: item.previewBg }}
          >
            {hasAsset ? (
              <img
                src={previewUrl}
                alt={item.label}
                className="max-h-20 max-w-full object-contain"
                onError={() => setHasAsset(false)}
              />
            ) : (
              <span className="text-xs" style={{ color: item.previewBg === "#ffffff" ? "#94a3b8" : "#93a0c4" }}>
                Nenhum asset enviado (usando padrão)
              </span>
            )}
          </div>
          <div className="flex gap-2">
            <input
              ref={inputRef}
              type="file"
              accept="image/png,image/jpeg,image/svg+xml,image/webp,image/x-icon"
              className="hidden"
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) handleFile(f);
                e.target.value = "";
              }}
            />
            <Button variant="primary" size="sm" onClick={() => inputRef.current?.click()} disabled={uploading} className="flex-1">
              {uploading ? <Loader2 size={14} className="animate-spin" /> : <Upload size={14} />}
              {hasAsset ? "Substituir" : "Enviar"}
            </Button>
            {hasAsset && (
              <Button variant="ghost" size="sm" onClick={handleDelete} disabled={uploading} title="Remover e voltar ao padrão">
                <Trash2 size={14} />
              </Button>
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

export default function BrandingUpload() {
  return (
    <div>
      <div className="mb-3">
        <h2 className="font-semibold text-gray-900">Marca / Branding</h2>
        <p className="mt-1 text-xs text-gray-500">
          Envie logo e favicon (PNG, JPEG, SVG, WEBP ou ICO até 2 MB). Os arquivos ficam no banco e são aplicados
          automaticamente no portal e no admin.
        </p>
      </div>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {ITEMS.map((item) => (
          <UploadCard key={item.key} item={item} />
        ))}
      </div>
    </div>
  );
}
