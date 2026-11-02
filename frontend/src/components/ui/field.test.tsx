// @vitest-environment jsdom
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { useEffect } from 'react';
import { useForm } from 'react-hook-form';
import { Field, FieldAction, FieldRow, FIELD_LABEL_SLOT, FIELD_NOTE } from './field';
import { Form, FormDescription, FormField, FormItem, FormLabel, FormControl, FormMessage } from './form';

describe('Field', () => {
  it('renders a fixed-height label slot with the field gap', () => {
    render(<Field label="Name"><input /></Field>);
    const slot = screen.getByText('Name').closest('[data-field-label]')!;
    expect(slot.className).toContain('h-[var(--field-label-h)]');
    expect(slot.className).toContain('mb-[var(--field-gap)]');
  });

  it('associates the label with the control (auto id and explicit id)', () => {
    const { unmount } = render(<Field label="Name"><input /></Field>);
    expect(screen.getByLabelText('Name')).toBeInTheDocument();
    unmount();
    render(<Field label="Phone" id="phone"><input id="phone" /></Field>);
    expect(screen.getByLabelText('Phone').id).toBe('phone');
  });

  it('wires aria-describedby to hint and error, error has role alert', () => {
    const { rerender } = render(<Field label="N" id="n" hint="Helpful"><input /></Field>);
    expect(screen.getByRole('textbox').getAttribute('aria-describedby')).toBe('n-note');
    expect(document.getElementById('n-note')?.textContent).toBe('Helpful');
    expect(screen.queryByRole('alert')).toBeNull();
    rerender(<Field label="N" id="n" hint="Helpful" error="Bad"><input /></Field>);
    expect(screen.getByRole('alert').textContent).toBe('Bad');
    expect(screen.getByRole('textbox').getAttribute('aria-invalid')).toBe('true');
  });

  it('reserveLabel renders an empty aria-hidden slot with identical sizing', () => {
    const { container } = render(
      <>
        <Field label="A"><input /></Field>
        <Field reserveLabel><button>x</button></Field>
      </>,
    );
    const slots = container.querySelectorAll('[data-field-label]');
    expect(slots).toHaveLength(2);
    expect(slots[1].getAttribute('aria-hidden')).toBe('true');
    expect(slots[1].textContent).toBe('');
    expect(slots[1].className).toBe(slots[0].className);
  });

  it('reserveNote keeps the helper row; note is text-micro with min height', () => {
    const { container } = render(<Field label="A" reserveNote><input /></Field>);
    const note = container.querySelector('[data-field-note]')!;
    expect(note.className).toContain('min-h-[var(--field-note-h)]');
    expect(note.className).toContain('text-micro');
    const { container: c2 } = render(<Field label="A"><input /></Field>);
    expect(c2.querySelector('[data-field-note]')).toBeNull();
  });

  it('shows the counter and flags overflow', () => {
    render(<Field label="A" counter={{ length: 5, max: 3 }}><input /></Field>);
    expect(screen.getByText('5/3').className).toContain('text-destructive');
  });

  it('supports a render-prop child receiving id and aria props', () => {
    render(<Field label="A" hint="h">{(p) => <input {...p} />}</Field>);
    expect(screen.getByLabelText('A').getAttribute('aria-describedby')).toBeTruthy();
  });
});

describe('FieldRow / FieldAction', () => {
  it('FieldRow aligns to the end with gap-3 and min-w-0 children', () => {
    const { container } = render(<FieldRow cols={2}><div /></FieldRow>);
    const row = container.firstElementChild!;
    expect(row.className).toContain('grid');
    expect(row.className).toContain('items-end');
    expect(row.className).toContain('gap-3');
    expect(row.className).toContain('[&>*]:min-w-0');
    expect(row.className).toContain('grid-cols-2');
  });

  it('FieldAction reserves the label slot', () => {
    const { container } = render(<FieldAction><button>Go</button></FieldAction>);
    expect(container.querySelector('[data-field-label][aria-hidden="true"]')).not.toBeNull();
  });
});

describe('FormItem parity', () => {
  function Harness({ error }: { error?: boolean }) {
    const form = useForm({ defaultValues: { a: '' } });
    useEffect(() => {
      if (error) form.setError('a', { message: 'Bad' });
    }, [error, form]);
    return (
      <Form {...form}>
        <FormField control={form.control} name="a" render={({ field }) => (
          <FormItem>
            <FormLabel>Name</FormLabel>
            <FormControl><input {...field} /></FormControl>
            <FormDescription>Desc</FormDescription>
            <FormMessage />
          </FormItem>
        )} />
      </Form>
    );
  }

  it('uses the same label-slot and note class tokens as Field', () => {
    render(<Harness />);
    const label = screen.getByText('Name');
    for (const t of FIELD_LABEL_SLOT.split(' ')) expect(label.className).toContain(t);
    const desc = screen.getByText('Desc');
    for (const t of FIELD_NOTE.split(' ')) expect(desc.className).toContain(t);
    expect(desc.className).not.toContain('0.8rem');
  });

  it('error message uses the note tokens and keeps aria wiring', async () => {
    render(<Harness error />);
    const msg = await screen.findByText('Bad');
    for (const t of FIELD_NOTE.split(' ')) expect(msg.className).toContain(t);
    expect(screen.getByRole('textbox').getAttribute('aria-invalid')).toBe('true');
  });
});

describe('tokens', () => {
  const css = readFileSync(resolve(__dirname, '../../index.css'), 'utf8');
  it('defines the field tokens in :root', () => {
    expect(css).toContain('--field-label-h: 16px');
    expect(css).toContain('--field-gap: 6px');
    expect(css).toContain('--field-note-h: 16px');
  });
  it('midnight has no 32/44 control overrides', () => {
    expect(css).not.toMatch(/--control-h-sm:\s*32px/);
    expect(css).not.toMatch(/--control-h-lg:\s*44px/);
    expect(css).not.toMatch(/--control-h-md:\s*38px/);
  });
});
