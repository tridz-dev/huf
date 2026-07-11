/**
 * Video — HUF extension to the AI Elements component set (shadcn conventions).
 *
 * Renders browser-playable video (MP4, WebM, Ogg, MOV, m4v, and data: URIs)
 * inline inside chat messages using the native HTML5 <video> element — no
 * third-party player dependency. On a playback error it degrades to a clean
 * fallback with Open / Download actions. Generic upload previews continue to
 * use the existing Attachment UI. Advanced streaming formats (HLS/DASH) and
 * provider embeds (YouTube/Vimeo) are intentionally NOT supported.
 *
 * This component is purely presentational — video *detection* (is a URL / MCP
 * tool result a video?) lives in `@/components/chat/videoDetection`.
 *
 * Wired into chat via:
 *  - ChatMessage.tsx     — `kind === 'Video'` renders <Video> for message.generatedVideo
 *  - tool.tsx ToolOutput — MCP tool results carrying a video URL render <Video> inline
 */
import { useState } from "react";
import type { ComponentPropsWithoutRef, ReactEventHandler } from "react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Download, ExternalLink, VideoOff } from "lucide-react";

export type VideoProps = ComponentPropsWithoutRef<"video"> & {
  src: string;
  title?: string;
  poster?: string;
  mediaType?: string;
  className?: string;
  captions?: Array<{ src: string; srcLang: string; label: string; default?: boolean }>;
  downloadName?: string;
  onError?: ReactEventHandler<HTMLVideoElement>;
};

export const Video = ({
  src,
  title,
  poster,
  mediaType,
  className,
  captions,
  downloadName,
  onError,
  controls = true,
  preload = "metadata",
  autoPlay = false,
  muted = false,
  loop = false,
  ...props
}: VideoProps) => {
  const [errored, setErrored] = useState(false);

  if (!src) {
    return null;
  }

  const handleError: ReactEventHandler<HTMLVideoElement> = (event) => {
    setErrored(true);
    // Strip the query string so we never log tokens/params from the URL.
    const safeSrc = src.split("?")[0];
    console.error("Video failed to play", {
      label: title || downloadName,
      mediaType,
      src: safeSrc,
    });
    onError?.(event);
  };

  // Browsers block autoplay-with-sound, so force muted when autoplaying.
  const effectiveMuted = autoPlay ? true : muted;

  if (errored) {
    const displayName = title || downloadName;
    return (
      <div
        className={cn(
          "w-full max-w-full overflow-hidden rounded-lg border bg-muted",
          className
        )}
      >
        <div className="flex flex-col gap-3 p-4">
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <VideoOff className="h-4 w-4" aria-hidden="true" />
            <span>Video could not be played</span>
          </div>
          {displayName && (
            <div
              className="truncate text-xs text-muted-foreground"
              title={displayName}
            >
              {displayName}
            </div>
          )}
          {src && (
            <div className="flex flex-wrap items-center gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() =>
                  window.open(src, "_blank", "noopener,noreferrer")
                }
              >
                <ExternalLink className="mr-1.5 h-4 w-4" />
                Open
              </Button>
              <Button variant="outline" size="sm" asChild>
                <a href={src} download={downloadName || ""}>
                  <Download className="mr-1.5 h-4 w-4" />
                  Download
                </a>
              </Button>
            </div>
          )}
        </div>
      </div>
    );
  }

  return (
    <div
      className={cn(
        "w-full max-w-full overflow-hidden rounded-lg border bg-muted",
        className
      )}
    >
      <video
        {...props}
        src={mediaType ? undefined : src}
        poster={poster}
        title={title}
        aria-label={title || downloadName || "Video"}
        controls={controls}
        preload={preload}
        autoPlay={autoPlay}
        muted={effectiveMuted}
        loop={loop}
        playsInline
        onError={handleError}
        className="block h-auto max-h-[70vh] w-full object-contain bg-black"
      >
        {mediaType && <source src={src} type={mediaType} />}
        {captions?.map((caption, index) => (
          <track
            key={`${caption.srcLang}-${caption.src}-${index}`}
            kind="captions"
            src={caption.src}
            srcLang={caption.srcLang}
            label={caption.label}
            default={caption.default}
          />
        ))}
      </video>
    </div>
  );
};
