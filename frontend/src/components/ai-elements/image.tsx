import { cn } from "@/lib/utils";
import type { Experimental_GeneratedImage } from "ai";
import { Button } from "@/components/ui/button";
import { DownloadIcon } from "lucide-react";
import { toast } from "sonner";

export type ImageProps = (Experimental_GeneratedImage & {
  className?: string;
  alt?: string;
  src?: never;
  showDownloadButton?: boolean;
}) | {
  src: string;
  className?: string;
  alt?: string;
  base64?: never;
  uint8Array?: never;
  mediaType?: never;
  showDownloadButton?: boolean;
};

export const Image = ({
  base64,
  uint8Array,
  mediaType,
  src,
  showDownloadButton = false,
  ...props
}: ImageProps) => {
  const imageSrc = src || (base64 && mediaType ? `data:${mediaType};base64,${base64}` : undefined);
  
  const handleDownload = async () => {
    if (!imageSrc) return;
    
    try {
      // Handle data URLs (base64)
      if (imageSrc.startsWith('data:')) {
        const response = await fetch(imageSrc);
        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = 'generated-image.png';
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        window.URL.revokeObjectURL(url);
        return;
      }
      
      // Handle regular URLs
      const response = await fetch(imageSrc);
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      // Extract filename from URL or use default
      try {
        const urlPath = new URL(imageSrc, window.location.origin).pathname;
        const filename = urlPath.split('/').pop() || 'generated-image.png';
        a.download = filename;
      } catch {
        a.download = 'generated-image.png';
      }
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      window.URL.revokeObjectURL(url);
    } catch (error) {
      console.error('Failed to download image:', error);
      toast.error('Failed to download image');
    }
  };

  if (!imageSrc) {
    return null;
  }

  return (
    <div className="relative group/image-container inline-block">
      <img
        {...props}
        alt={props.alt}
        className={cn(
          "h-auto max-w-full overflow-hidden rounded-md",
          props.className
        )}
        src={imageSrc}
      />
      {showDownloadButton && (
        <div className="absolute top-2 right-2 opacity-0 group-hover/image-container:opacity-100 transition-opacity">
          <Button
            variant="secondary"
            size="icon-sm"
            className="bg-white backdrop-blur-sm shadow-md"
            onClick={handleDownload}
            title="Download image"
          >
            <DownloadIcon className="h-4 w-4" />
            <span className="sr-only">Download image</span>
          </Button>
        </div>
      )}
    </div>
  );
};
