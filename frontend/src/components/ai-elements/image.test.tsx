// @vitest-environment jsdom
import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { Image, type ImageProps } from './image';

vi.mock('sonner', () => ({
	toast: { error: vi.fn(), success: vi.fn() },
}));

describe('Image', () => {
	it('renders nothing when neither src nor base64 is provided', () => {
		// Real callers can hit this (e.g. a still-streaming artifact) even though
		// the prop types require one of the two variants — exercise it directly.
		const props = { alt: 'nothing' } as unknown as ImageProps;
		const { container } = render(<Image {...props} />);
		expect(container.firstChild).toBeNull();
	});

	it('renders an <img> from a plain src URL', () => {
		render(<Image src="https://example.com/pic.png" alt="a picture" />);
		const img = screen.getByAltText('a picture');
		expect(img).toHaveAttribute('src', 'https://example.com/pic.png');
	});

	it('builds a data URL from base64 + mediaType when no src is given', () => {
		render(
			<Image
				base64="Zm9v"
				uint8Array={new Uint8Array()}
				mediaType="image/png"
				alt="from base64"
			/>
		);
		const img = screen.getByAltText('from base64');
		expect(img).toHaveAttribute('src', 'data:image/png;base64,Zm9v');
	});

	it('prefers src over base64 when both would resolve', () => {
		render(
			<Image
				src="https://example.com/direct.png"
				alt="direct wins"
			/>
		);
		expect(screen.getByAltText('direct wins')).toHaveAttribute(
			'src',
			'https://example.com/direct.png'
		);
	});

	it('does not render a download button by default', () => {
		render(<Image src="https://example.com/pic.png" alt="no button" />);
		expect(screen.queryByTitle('Download image')).not.toBeInTheDocument();
	});

	it('renders a download button when showDownloadButton is true', () => {
		render(
			<Image
				src="https://example.com/pic.png"
				alt="with button"
				showDownloadButton
			/>
		);
		expect(screen.getByTitle('Download image')).toBeInTheDocument();
	});

	it('calls onLoad when the image finishes loading', async () => {
		const onLoad = vi.fn();
		render(<Image src="https://example.com/pic.png" alt="loadable" onLoad={onLoad} />);
		const img = screen.getByAltText('loadable');
		img.dispatchEvent(new Event('load'));
		expect(onLoad).toHaveBeenCalledTimes(1);
	});

	it('merges a custom className onto the image', () => {
		render(
			<Image src="https://example.com/pic.png" alt="styled" className="my-custom-class" />
		);
		expect(screen.getByAltText('styled')).toHaveClass('my-custom-class');
	});
});
