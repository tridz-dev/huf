import { useEffect, useState } from 'react';
import { GitBranch, Loader2, Upload, Globe } from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import {
  importSkillFromGit,
  importSkillFromCommonDestination,
  importSkillFromHuf,
  getSkillDestinations,
  type SkillDestination,
} from '@/services/skillApi';
import { getFrappeErrorMessage } from '@/lib/frappe-error';
import { toast } from 'sonner';

interface SkillImportModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSuccess?: () => void;
}

export function SkillImportModal({ open, onOpenChange, onSuccess }: SkillImportModalProps) {
  const [activeTab, setActiveTab] = useState('git');
  const [repoUrl, setRepoUrl] = useState('');
  const [path, setPath] = useState('skills');
  const [ref, setRef] = useState('main');
  const [destinationName, setDestinationName] = useState('');
  const [destinations, setDestinations] = useState<SkillDestination[]>([]);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (open) {
      getSkillDestinations()
        .then((data) => setDestinations(data || []))
        .catch(() => setDestinations([]));
    }
  }, [open]);

  const resetForm = () => {
    setRepoUrl('');
    setPath('skills');
    setRef('main');
    setDestinationName('');
    setSelectedFile(null);
    setActiveTab('git');
  };

  const handleClose = () => {
    if (!loading) {
      onOpenChange(false);
      resetForm();
    }
  };

  const handleGitImport = async () => {
    if (!repoUrl.trim()) {
      toast.error('Repository URL is required');
      return;
    }
    setLoading(true);
    try {
      const result = await importSkillFromGit(repoUrl.trim(), path.trim() || 'skills', ref.trim() || 'main');
      if (result.success) {
        toast.success(result.message || 'Skills imported successfully');
        onSuccess?.();
        handleClose();
      } else {
        toast.error(result.message || 'Import failed');
      }
    } catch (error) {
      toast.error(getFrappeErrorMessage(error) || 'Failed to import skills from Git');
    } finally {
      setLoading(false);
    }
  };

  const handleCommonImport = async () => {
    if (!destinationName.trim()) {
      toast.error('Destination name is required');
      return;
    }
    setLoading(true);
    try {
      const result = await importSkillFromCommonDestination(destinationName.trim());
      if (result.success) {
        toast.success(result.message || 'Skills imported successfully');
        onSuccess?.();
        handleClose();
      } else {
        toast.error(result.message || 'Import failed');
      }
    } catch (error) {
      toast.error(getFrappeErrorMessage(error) || 'Failed to import skills from common destination');
    } finally {
      setLoading(false);
    }
  };

  const handleHufImport = async () => {
    if (!selectedFile) {
      toast.error('Please select a .huf file');
      return;
    }
    setLoading(true);
    try {
      const result = await importSkillFromHuf(selectedFile);
      if (result.skill) {
        toast.success(`Skill '${result.skill}' imported successfully`);
        onSuccess?.();
        handleClose();
      } else {
        toast.error(result.message || 'Import failed');
      }
    } catch (error) {
      toast.error(getFrappeErrorMessage(error) || 'Failed to import skill from .huf');
    } finally {
      setLoading(false);
    }
  };

  const handleImport = () => {
    if (activeTab === 'git') return handleGitImport();
    if (activeTab === 'huf') return handleHufImport();
    return handleCommonImport();
  };

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Import skills</DialogTitle>
          <DialogDescription>
            Import skills from a Git repository or a configured common destination.
          </DialogDescription>
        </DialogHeader>

        <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
          <TabsList className="grid w-full grid-cols-3">
            <TabsTrigger value="git">
              <GitBranch className="w-4 h-4 mr-2" />
              Git
            </TabsTrigger>
            <TabsTrigger value="common">
              <Globe className="w-4 h-4 mr-2" />
              Common
            </TabsTrigger>
            <TabsTrigger value="huf">
              <Upload className="w-4 h-4 mr-2" />
              Upload .huf
            </TabsTrigger>
          </TabsList>

          <TabsContent value="git" className="space-y-4 mt-4">
            <div className="space-y-2">
              <Label htmlFor="repo_url">Repository URL</Label>
              <Input
                id="repo_url"
                placeholder="https://github.com/org/repo"
                value={repoUrl}
                onChange={(e) => setRepoUrl(e.target.value)}
                disabled={loading}
              />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="path">Path</Label>
                <Input
                  id="path"
                  placeholder="skills"
                  value={path}
                  onChange={(e) => setPath(e.target.value)}
                  disabled={loading}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="ref">Ref</Label>
                <Input
                  id="ref"
                  placeholder="main"
                  value={ref}
                  onChange={(e) => setRef(e.target.value)}
                  disabled={loading}
                />
              </div>
            </div>
          </TabsContent>

          <TabsContent value="common" className="space-y-4 mt-4">
            <div className="space-y-2">
              <Label htmlFor="destination_name">Destination</Label>
              <Select
                value={destinationName || '__none'}
                onValueChange={(value) => setDestinationName(value === '__none' ? '' : value)}
                disabled={loading}
              >
                <SelectTrigger id="destination_name">
                  <SelectValue placeholder="Select a destination..." />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="__none" disabled>
                    Select a destination...
                  </SelectItem>
                  {destinations.map((dest) => (
                    <SelectItem key={dest.name} value={dest.name}>
                      {dest.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {destinations.length === 0 && (
                <p className="text-xs text-muted-foreground">
                  No destinations configured. Add one in Agent Settings.
                </p>
              )}
            </div>
          </TabsContent>

          <TabsContent value="huf" className="space-y-4 mt-4">
            <div className="space-y-2">
              <Label htmlFor="huf_file">Skill package (.huf)</Label>
              <Input
                id="huf_file"
                type="file"
                accept=".huf"
                onChange={(e) => setSelectedFile(e.target.files?.[0] || null)}
                disabled={loading}
              />
              <p className="text-xs text-muted-foreground">
                Select a .huf file exported from Huf.
              </p>
            </div>
          </TabsContent>
        </Tabs>

        <DialogFooter>
          <Button variant="outline" onClick={handleClose} disabled={loading}>
            Cancel
          </Button>
          <Button onClick={handleImport} disabled={loading}>
            {loading && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}
            Import
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export default SkillImportModal;
