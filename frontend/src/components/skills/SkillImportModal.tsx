import { useState } from 'react';
import { GitBranch, Download, Loader2 } from 'lucide-react';
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
import { importSkillFromGit, importSkillFromCommonDestination } from '@/services/skillApi';
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
  const [loading, setLoading] = useState(false);

  const resetForm = () => {
    setRepoUrl('');
    setPath('skills');
    setRef('main');
    setDestinationName('');
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

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Import Skills</DialogTitle>
          <DialogDescription>
            Import skills from a Git repository or a configured common destination.
          </DialogDescription>
        </DialogHeader>

        <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
          <TabsList className="grid w-full grid-cols-2">
            <TabsTrigger value="git">
              <GitBranch className="w-4 h-4 mr-2" />
              Git
            </TabsTrigger>
            <TabsTrigger value="common">
              <Download className="w-4 h-4 mr-2" />
              Common Destination
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
              <Label htmlFor="destination_name">Destination Name</Label>
              <Input
                id="destination_name"
                placeholder="tridz-dev/huf-skills"
                value={destinationName}
                onChange={(e) => setDestinationName(e.target.value)}
                disabled={loading}
              />
            </div>
          </TabsContent>
        </Tabs>

        <DialogFooter>
          <Button variant="outline" onClick={handleClose} disabled={loading}>
            Cancel
          </Button>
          <Button
            onClick={activeTab === 'git' ? handleGitImport : handleCommonImport}
            disabled={loading}
          >
            {loading && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}
            Import
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export default SkillImportModal;
