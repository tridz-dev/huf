"use client";

import type { Experimental_SpeechResult as SpeechResult } from "ai";
import type { ComponentProps, CSSProperties } from "react";

import { Button } from "@/components/ui/button";

import { cn } from "@/lib/utils";
import {
  MediaControlBar,
  MediaController,
  MediaDurationDisplay,
  MediaMuteButton,
  MediaPlayButton,
  MediaSeekBackwardButton,
  MediaSeekForwardButton,
  MediaTimeDisplay,
  MediaTimeRange,
  MediaVolumeRange,
} from "media-chrome/react";

export type AudioPlayerProps = Omit<
  ComponentProps<typeof MediaController>,
  "audio"
>;

export const AudioPlayer = ({
  children,
  style,
  ...props
}: AudioPlayerProps) => (
  <MediaController
    audio
    data-slot="audio-player"
    style={
      {
        "--media-background-color": "transparent",
        "--media-button-icon-height": "1rem",
        "--media-button-icon-width": "1rem",
        "--media-control-background": "transparent",
        "--media-control-hover-background": "var(--color-accent)",
        "--media-control-padding": "0",
        "--media-font": "var(--font-sans)",
        "--media-font-size": "10px",
        "--media-icon-color": "currentColor",
        "--media-preview-time-background": "var(--color-background)",
        "--media-preview-time-border-radius": "var(--radius-md)",
        "--media-preview-time-text-shadow": "none",
        "--media-primary-color": "hsl(var(--primary))",
        "--media-range-bar-color": "hsl(var(--primary))",
        "--media-range-thumb-background": "hsl(var(--primary))",
        "--media-range-track-background": "hsl(var(--primary) / 0.2)",
        "--media-secondary-color": "hsl(var(--secondary))",
        "--media-text-color": "hsl(var(--foreground))",
        "--media-tooltip-arrow-display": "none",
        "--media-tooltip-background": "hsl(var(--background))",
        "--media-tooltip-border-radius": "var(--radius)",
        ...style,
      } as CSSProperties
    }
    {...props}
  >
    {children}
  </MediaController>
);

export type AudioPlayerElementProps = Omit<ComponentProps<"audio">, "src"> &
  (
    | {
      data: SpeechResult["audio"];
    }
    | {
      src: string;
    }
  );

export const AudioPlayerElement = ({ ...props }: AudioPlayerElementProps) => (
  // oxlint-disable-next-line eslint-plugin-jsx-a11y(media-has-caption) -- audio player captions are provided by consumer
  <audio
    data-slot="audio-player-element"
    slot="media"
    src={
      "src" in props
        ? props.src
        : `data:${props.data.mediaType};base64,${props.data.base64}`
    }
    {...props}
  />
);

export type AudioPlayerControlBarProps = ComponentProps<typeof MediaControlBar>;

export const AudioPlayerControlBar = ({
  children,
  ...props
}: AudioPlayerControlBarProps) => (
  <MediaControlBar data-slot="audio-player-control-bar" className={cn("flex w-[400px] max-w-full items-center gap-1 sm:gap-2 rounded-full border bg-secondary/30 px-2 py-1.5 shadow-sm backdrop-blur-sm", props.className)} {...props}>
    {children}
  </MediaControlBar>
);

export type AudioPlayerPlayButtonProps = ComponentProps<typeof MediaPlayButton>;

export const AudioPlayerPlayButton = ({
  className,
  ...props
}: AudioPlayerPlayButtonProps) => (
  <Button asChild size="icon" variant="ghost" className="h-8 w-8 rounded-full hover:bg-background/80">
    <MediaPlayButton
      className={cn("bg-transparent text-foreground", className)}
      data-slot="audio-player-play-button"
      {...props}
    />
  </Button>
);

export type AudioPlayerSeekBackwardButtonProps = ComponentProps<
  typeof MediaSeekBackwardButton
>;

export const AudioPlayerSeekBackwardButton = ({
  seekOffset = 10,
  ...props
}: AudioPlayerSeekBackwardButtonProps) => (
  <Button asChild size="icon" variant="ghost" className="h-8 w-8 rounded-full hover:bg-background/80">
    <MediaSeekBackwardButton
      className={cn("bg-transparent text-foreground", props.className)}
      data-slot="audio-player-seek-backward-button"
      seekOffset={seekOffset}
      {...props}
    />
  </Button>
);

export type AudioPlayerSeekForwardButtonProps = ComponentProps<
  typeof MediaSeekForwardButton
>;

export const AudioPlayerSeekForwardButton = ({
  seekOffset = 10,
  ...props
}: AudioPlayerSeekForwardButtonProps) => (
  <Button asChild size="icon" variant="ghost" className="h-8 w-8 rounded-full hover:bg-background/80">
    <MediaSeekForwardButton
      className={cn("bg-transparent text-foreground", props.className)}
      data-slot="audio-player-seek-forward-button"
      seekOffset={seekOffset}
      {...props}
    />
  </Button>
);

export type AudioPlayerTimeDisplayProps = ComponentProps<
  typeof MediaTimeDisplay
>;

export const AudioPlayerTimeDisplay = ({
  className,
  ...props
}: AudioPlayerTimeDisplayProps) => (
  <div className="flex items-center px-1">
    <MediaTimeDisplay
      className={cn("tabular-nums text-xs font-medium text-foreground/80 bg-transparent", className)}
      data-slot="audio-player-time-display"
      {...props}
    />
  </div>
);

export type AudioPlayerTimeRangeProps = ComponentProps<typeof MediaTimeRange>;

export const AudioPlayerTimeRange = ({
  className,
  ...props
}: AudioPlayerTimeRangeProps) => (
  <div className="flex h-8 flex-1 items-center px-1">
    <MediaTimeRange
      className={cn("bg-transparent", className)}
      data-slot="audio-player-time-range"
      {...props}
    />
  </div>
);

export type AudioPlayerDurationDisplayProps = ComponentProps<
  typeof MediaDurationDisplay
>;

export const AudioPlayerDurationDisplay = ({
  className,
  ...props
}: AudioPlayerDurationDisplayProps) => (
  <div className="flex items-center px-1">
    <MediaDurationDisplay
      className={cn("tabular-nums text-xs font-medium text-foreground/50 bg-transparent", className)}
      data-slot="audio-player-duration-display"
      {...props}
    />
  </div>
);

export type AudioPlayerMuteButtonProps = ComponentProps<typeof MediaMuteButton>;

export const AudioPlayerMuteButton = ({
  className,
  ...props
}: AudioPlayerMuteButtonProps) => (
  <Button asChild size="icon" variant="ghost" className="h-8 w-8 rounded-full hover:bg-background/80">
    <MediaMuteButton
      className={cn("bg-transparent text-foreground/70 hover:text-foreground", className)}
      data-slot="audio-player-mute-button"
      {...props}
    />
  </Button>
);

export type AudioPlayerVolumeRangeProps = ComponentProps<
  typeof MediaVolumeRange
>;

export const AudioPlayerVolumeRange = ({
  className,
  ...props
}: AudioPlayerVolumeRangeProps) => (
  <div className="flex h-8 w-20 items-center px-1">
    <MediaVolumeRange
      className={cn("bg-transparent", className)}
      data-slot="audio-player-volume-range"
      {...props}
    />
  </div>
);
