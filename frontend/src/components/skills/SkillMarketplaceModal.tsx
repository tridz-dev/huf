import { useEffect, useState } from 'react';
import { Store, Loader2, Download, Search } from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import {
  fetchSkillRegistry,
  importSkillFromRegistry,
  type SkillRegistry,
  type SkillRegistrySkill,
} from '@/services/skillApi';
import { getFrappeErrorMessage } from '@/lib/frappe-error';
import { toast } from 'sonner';

interface SkillMarketplaceModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSuccess?: () => void;
}

const DEFAULT_REGISTRY_URL = 'https://github.com/tridz-dev/huf-skills';

export function SkillMarketplaceModal({ open, onOpenChange, onSuccess }: SkillMarketplaceModalProps) {
  const [registry, setRegistry] = useState<SkillRegistry | null>(null);
  const [loading, setLoading] = useState(false);
  const [installing, setInstalling] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setLoading(true);
    setError(null);
    fetchSkillRegistry(DEFAULT_REGISTRY_URL)
      .then((data) => setRegistry(data || null))
      .catch((err) => {
        setError(getFrappeErrorMessage(err) || 'Failed to load marketplace');
        toast.error('Failed to load skill marketplace');
      })
      .finally(() => setLoading(false));
  }, [open]);

  const handleInstall = async (skill: SkillRegistrySkill) => {
    setInstalling(skill.name);
    try {
      const result = await importSkillFromRegistry(
        DEFAULT_REGISTRY_URL,
        skill.name,
        registry?.skills_path || 'skills',
        registry?.ref || 'main'
      );
      if (result.success !== false) {
        toast.success(`'${skill.title || skill.name}' installed`);
        onSuccess?.();
      } else {
        toast.error(result.message || 'Install failed');
      }
    } catch (err) {
      toast.error(getFrappeErrorMessage(err) || 'Failed to install skill');
    } finally {
      setInstalling(null);
    }
  };

  const filteredSkills = (registry?.skills || []).filter((skill) => {
    const term = search.toLowerCase();
    return (
      (skill.name || '').toLowerCase().includes(term) ||
      (skill.title || '').toLowerCase().includes(term) ||
      (skill.description || '').toLowerCase().includes(term)
    );
  });

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-2xl max-h-[80vh] flex flex-col">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Store className="w-5 h-5" />
            Skills Marketplace
          </DialogTitle>
          <DialogDescription>
            Browse and install curated skills from the Huf marketplace.
          </DialogDescription>
        </DialogHeader>

        <div className="relative mt-2">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
          <Input
            placeholder="Search marketplace..."
            className="pl-9"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>

        <div className="flex-1 overflow-y-auto mt-4 space-y-3 pr-1">
          {loading && (
            <div className="flex items-center justify-center py-12 text-muted-foreground">
              <Loader2 className="w-5 h-5 mr-2 animate-spin" />
              Loading marketplace...
            </div>
          )}

          {!loading && error && (
            <div className="text-center py-12">
              <p className="text-destructive mb-2">Failed to load marketplace</p>
              <p className="text-sm text-muted-foreground">{error}</p>
            </div>
          )}

          {!loading && !error && filteredSkills.length === 0 && (
            <div className="text-center py-12 text-muted-foreground">
              {search ? 'No skills match your search.' : 'No skills available in this registry.'}
            </div>
          )}

          {filteredSkills.map((skill) => (
            <div
              key={skill.name}
              className="flex items-start justify-between gap-4 rounded-lg border p-4 hover:bg-muted/50"
            >
              <div className="min-w-0 space-y-1">
                <div className="flex items-center gap-2 flex-wrap">
                  <p className="font-medium text-sm">{skill.title || skill.name}</p>
                  {skill.category && (
                    <Badge variant="secondary" className="text-[10px]">
                      {skill.category}
                    </Badge>
                  )}
                </div>
                {skill.description && (
                  <p className="text-xs text-muted-foreground line-clamp-2">{skill.description}</p>
                )}
                <p className="text-xs text-muted-foreground">
                  {skill.author || 'Unknown'} {skill.version ? `· v${skill.version}` : ''}
                </p>
              </div>
              <Button
                size="sm"
                variant="outline"
                onClick={() => handleInstall(skill)}
                disabled={installing === skill.name}
              >
                {installing === skill.name ? (
                  <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                ) : (
                  <Download className="w-4 h-4 mr-2" />
                )}
                {installing === skill.name ? 'Installing...' : 'Install'}
              </Button>
            </div>
          ))}
        </div>
      </DialogContent>
    </Dialog>
  );
}

export default SkillMarketplaceModal;
