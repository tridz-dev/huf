// @vitest-environment jsdom
import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import type { CSSProperties } from 'react';
import {
	AudioPlayer,
	AudioPlayerElement,
	AudioPlayerControlBar,
	AudioPlayerPlayButton,
	AudioPlayerSeekBackwardButton,
	AudioPlayerSeekForwardButton,
	AudioPlayerTimeDisplay,
	AudioPlayerTimeRange,
	AudioPlayerDurationDisplay,
	AudioPlayerMuteButton,
	AudioPlayerVolumeRange,
	type AudioPlayerElementProps,
} from './audio-player';

describe('AudioPlayer', () => {
	it('renders a media-controller with the audio-player data slot and its children', () => {
		const { container } = render(
			<AudioPlayer>
				<AudioPlayerElement src="/files/a.mp3" />
			</AudioPlayer>
		);
		const controller = container.querySelector('[data-slot="audio-player"]');
		expect(controller).toBeInTheDocument();
		expect(controller?.tagName.toLowerCase()).toBe('media-controller');
		expect(container.querySelector('audio')).toBeInTheDocument();
	});

	it('merges custom style overrides on top of the default CSS variables', () => {
		const { container } = render(
			<AudioPlayer
				style={{ '--media-primary-color': 'red', color: 'blue' } as CSSProperties}
			>
				<AudioPlayerElement src="/files/a.mp3" />
			</AudioPlayer>
		);
		const controller = container.querySelector(
			'[data-slot="audio-player"]'
		) as HTMLElement;
		// Consumer override wins over the default value
		expect(controller.style.getPropertyValue('--media-primary-color')).toBe('red');
		// Untouched defaults are preserved
		expect(controller.style.getPropertyValue('--media-font-size')).toBe('0.75rem');
		expect(controller.style.color).toBe('blue');
	});

	it('forwards extra props (className) to the media-controller', () => {
		const { container } = render(
			<AudioPlayer className="my-player">
				<AudioPlayerElement src="/files/a.mp3" />
			</AudioPlayer>
		);
		expect(container.querySelector('[data-slot="audio-player"]')).toHaveClass('my-player');
	});
});

describe('AudioPlayerElement', () => {
	it('uses the src directly for the src variant', () => {
		const { container } = render(<AudioPlayerElement src="/files/song.mp3" />);
		const audio = container.querySelector('audio');
		expect(audio).toHaveAttribute('src', '/files/song.mp3');
		expect(audio).toHaveAttribute('slot', 'media');
		expect(audio).toHaveAttribute('data-slot', 'audio-player-element');
	});

	it('builds a data URL from base64 audio data for the data variant', () => {
		// AudioPlayerElementProps is a discriminated union (data | src), so
		// there's no single `.data` field to index off the type directly —
		// Extract the data-carrying branch instead.
		const data: Extract<AudioPlayerElementProps, { data: unknown }>['data'] = {
			base64: 'QUJD',
			mediaType: 'audio/mpeg',
			format: 'mp3',
			uint8Array: new Uint8Array(),
		};
		const { container } = render(<AudioPlayerElement data={data} />);
		expect(container.querySelector('audio')).toHaveAttribute(
			'src',
			'data:audio/mpeg;base64,QUJD'
		);
	});
});

describe('AudioPlayer seek buttons', () => {
	it('defaults the backward seek offset to 10 seconds', () => {
		const { container } = render(<AudioPlayerSeekBackwardButton />);
		const button = container.querySelector('[data-slot="audio-player-seek-backward-button"]');
		expect(button).toBeInTheDocument();
		expect(button?.getAttribute('seekoffset')).toBe('10');
	});

	it('honours a custom forward seek offset', () => {
		const { container } = render(<AudioPlayerSeekForwardButton seekOffset={30} />);
		const button = container.querySelector('[data-slot="audio-player-seek-forward-button"]');
		expect(button).toBeInTheDocument();
		expect(button?.getAttribute('seekoffset')).toBe('30');
	});
});

describe('AudioPlayerControlBar', () => {
	it('renders the control bar wrapper around its children', () => {
		const { container } = render(
			<AudioPlayerControlBar>
				<button type="button">inner control</button>
			</AudioPlayerControlBar>
		);
		const bar = container.querySelector('[data-slot="audio-player-control-bar"]');
		expect(bar).toBeInTheDocument();
		expect(screen.getByRole('button', { name: 'inner control' })).toBeInTheDocument();
	});
});

describe('AudioPlayer controls', () => {
	it('renders every control with its data slot inside a full player', () => {
		const { container } = render(
			<AudioPlayer>
				<AudioPlayerElement src="/files/a.mp3" />
				<AudioPlayerControlBar>
					<AudioPlayerPlayButton />
					<AudioPlayerTimeDisplay />
					<AudioPlayerTimeRange />
					<AudioPlayerDurationDisplay />
					<AudioPlayerMuteButton />
					<AudioPlayerVolumeRange />
				</AudioPlayerControlBar>
			</AudioPlayer>
		);
		for (const slot of [
			'audio-player-play-button',
			'audio-player-time-display',
			'audio-player-time-range',
			'audio-player-duration-display',
			'audio-player-mute-button',
			'audio-player-volume-range',
		]) {
			expect(container.querySelector(`[data-slot="${slot}"]`)).toBeInTheDocument();
		}
	});

	it('merges a custom className onto the play button', () => {
		const { container } = render(<AudioPlayerPlayButton className="extra-class" />);
		const button = container.querySelector('[data-slot="audio-player-play-button"]');
		expect(button).toHaveClass('bg-transparent');
		expect(button).toHaveClass('extra-class');
	});
});
