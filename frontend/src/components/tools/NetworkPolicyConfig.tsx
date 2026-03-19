import { type ReactNode } from 'react';
import { Globe, Lock, List, X } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Badge } from '@/components/ui/badge';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';

// ---------------------------------------------------------------------------
// Preset registry (must mirror sandbox_policy.py:PRESET_DOMAINS)
// ---------------------------------------------------------------------------

export const NETWORK_PRESETS = [
  { id: 'npm',    label: 'npm / yarn',     description: 'npmjs.org, yarnpkg.com' },
  { id: 'pip',    label: 'pip / PyPI',     description: 'pypi.org, pythonhosted.org' },
  { id: 'apt',    label: 'apt / Ubuntu',   description: 'archive.ubuntu.com, deb.debian.org' },
  { id: 'brew',   label: 'Homebrew',       description: 'formulae.brew.sh, github.com' },
  { id: 'docker', label: 'Docker Hub',     description: 'registry-1.docker.io' },
  { id: 'cargo',  label: 'Cargo / Rust',   description: 'crates.io, static.crates.io' },
  { id: 'gem',    label: 'RubyGems',       description: 'rubygems.org' },
  { id: 'go',     label: 'Go modules',     description: 'proxy.golang.org' },
  { id: 'maven',  label: 'Maven Central',  description: 'repo1.maven.org' },
  { id: 'nuget',  label: 'NuGet',          description: 'api.nuget.org' },
] as const;

export type NetworkPresetId = (typeof NETWORK_PRESETS)[number]['id'];
export type NetworkMode = 'disabled' | 'whitelist' | 'open';

// ---------------------------------------------------------------------------
// Mode selector sub-component
// ---------------------------------------------------------------------------

const MODE_OPTIONS: { value: NetworkMode; label: string; icon: ReactNode; description: string }[] = [
  {
    value: 'disabled',
    label: 'Disabled',
    icon: <Lock className="w-4 h-4" />,
    description: 'No outbound network — fully air-gapped',
  },
  {
    value: 'whitelist',
    label: 'Whitelist',
    icon: <List className="w-4 h-4" />,
    description: 'Allow specific registries & domains only',
  },
  {
    value: 'open',
    label: 'Open',
    icon: <Globe className="w-4 h-4" />,
    description: 'Full outbound access (no restrictions)',
  },
];

interface ModeSelectorProps {
  value: NetworkMode;
  onChange: (mode: NetworkMode) => void;
  disabled?: boolean;
}

function ModeSelector({ value, onChange, disabled }: ModeSelectorProps) {
  return (
    <div className="grid grid-cols-3 gap-2">
      {MODE_OPTIONS.map((opt) => (
        <button
          key={opt.value}
          type="button"
          disabled={disabled}
          onClick={() => onChange(opt.value)}
          className={cn(
            'flex flex-col items-center gap-1.5 rounded-lg border p-3 text-sm transition-colors',
            'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
            value === opt.value
              ? 'border-purple-600 bg-purple-50 text-purple-900'
              : 'border-border bg-background text-muted-foreground hover:border-muted-foreground/50',
            disabled && 'cursor-not-allowed opacity-50',
          )}
        >
          {opt.icon}
          <span className="font-medium">{opt.label}</span>
          <span className="text-[10px] text-center leading-tight opacity-70">{opt.description}</span>
        </button>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Preset toggle chip
// ---------------------------------------------------------------------------

interface PresetChipProps {
  preset: { id: string; label: string; description: string };
  selected: boolean;
  onToggle: (id: NetworkPresetId) => void;
  disabled?: boolean;
}

function PresetChip({ preset, selected, onToggle, disabled }: PresetChipProps) {
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={() => onToggle(preset.id)}
      title={preset.description}
      className={cn(
        'inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-medium transition-colors',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
        selected
          ? 'border-purple-600 bg-purple-100 text-purple-900'
          : 'border-border bg-muted text-muted-foreground hover:border-muted-foreground/50',
        disabled && 'cursor-not-allowed opacity-50',
      )}
    >
      {selected && <X className="w-3 h-3" />}
      {preset.label}
    </button>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export interface NetworkPolicyValue {
  network_mode: NetworkMode;
  /** JSON-encoded array of preset ids, e.g. '["pip","npm"]' */
  network_presets: string;
  /** Newline-separated extra domains */
  allowed_domains: string;
}

interface NetworkPolicyConfigProps {
  value: NetworkPolicyValue;
  onChange: (value: NetworkPolicyValue) => void;
  disabled?: boolean;
}

export function NetworkPolicyConfig({ value, onChange, disabled }: NetworkPolicyConfigProps) {
  // Parse presets from JSON string stored in form
  const selectedPresets: NetworkPresetId[] = (() => {
    try {
      const parsed = JSON.parse(value.network_presets || '[]');
      return Array.isArray(parsed) ? (parsed as NetworkPresetId[]) : [];
    } catch {
      return [];
    }
  })();

  const handleModeChange = (mode: NetworkMode) => {
    onChange({ ...value, network_mode: mode });
  };

  const handlePresetToggle = (id: NetworkPresetId) => {
    const next = selectedPresets.includes(id)
      ? selectedPresets.filter((p) => p !== id)
      : [...selectedPresets, id];
    onChange({ ...value, network_presets: JSON.stringify(next) });
  };

  const handleDomainsChange = (raw: string) => {
    onChange({ ...value, allowed_domains: raw });
  };

  const showWhitelistOptions = value.network_mode === 'whitelist';

  return (
    <div className="space-y-4">
      {/* Mode selector */}
      <div className="space-y-2">
        <Label>Network Access</Label>
        <ModeSelector value={value.network_mode} onChange={handleModeChange} disabled={disabled} />
      </div>

      {/* Whitelist options — only visible in whitelist mode */}
      {showWhitelistOptions && (
        <div className="space-y-4 rounded-lg border border-purple-200 bg-purple-50/50 p-4">
          {/* Preset toggles */}
          <div className="space-y-2">
            <Label className="text-sm">Package registries</Label>
            <p className="text-xs text-muted-foreground">
              Toggle to allow the registry's well-known domains inside the sandbox.
            </p>
            <div className="flex flex-wrap gap-2 pt-1">
              {NETWORK_PRESETS.map((preset) => (
                <PresetChip
                  key={preset.id}
                  preset={preset}
                  selected={selectedPresets.includes(preset.id)}
                  onToggle={handlePresetToggle}
                  disabled={disabled}
                />
              ))}
            </div>
            {selectedPresets.length > 0 && (
              <div className="flex flex-wrap gap-1 pt-1">
                <span className="text-xs text-muted-foreground">Active:</span>
                {selectedPresets.map((id) => (
                  <Badge key={id} variant="outline" className="text-[10px]">
                    {id}
                  </Badge>
                ))}
              </div>
            )}
          </div>

          {/* Custom domain list */}
          <div className="space-y-2">
            <Label className="text-sm">Additional domains</Label>
            <p className="text-xs text-muted-foreground">
              One domain per line. Example: <span className="font-mono">api.myservice.com</span>
            </p>
            <Textarea
              placeholder={'api.myservice.com\nhuggingface.co'}
              value={value.allowed_domains}
              onChange={(e) => handleDomainsChange(e.target.value)}
              disabled={disabled}
              className="min-h-[80px] font-mono text-xs"
            />
          </div>
        </div>
      )}

      {/* Open mode warning */}
      {value.network_mode === 'open' && (
        <div className="rounded-lg border border-amber-300 bg-amber-50 px-4 py-3 text-xs text-amber-900">
          <strong>Unrestricted outbound access</strong> — the sandbox can reach any external host.
          Only use this when the code is fully trusted.
        </div>
      )}
    </div>
  );
}
