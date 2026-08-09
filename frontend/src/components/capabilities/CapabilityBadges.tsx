import { Badge } from '@/components/ui/badge';
import type {
  CapabilityDescriptor,
  CapabilitySourceType,
  MutationLevel,
  CapabilityVisibility,
} from '@/types/capability.types';

const SOURCE_TYPE_LABEL: Record<CapabilitySourceType, string> = {
  declared: 'Declared',
  framework_discovered: 'Framework',
  generated: 'Generated',
  inferred: 'Inferred',
};

const MUTATION_LEVEL_LABEL: Record<MutationLevel, string> = {
  read: 'Read',
  write: 'Write',
  destructive: 'Destructive',
  unknown: 'Unknown',
};

const MUTATION_LEVEL_VARIANT: Record<MutationLevel, 'default' | 'secondary' | 'destructive' | 'success'> = {
  read: 'success',
  write: 'secondary',
  destructive: 'destructive',
  unknown: 'default',
};

const VISIBILITY_LABEL: Record<CapabilityVisibility, string> = {
  recommended: 'Recommended',
  normal: 'Normal',
  advanced: 'Advanced',
  hidden: 'Hidden',
};

interface CapabilityBadgesProps {
  capability: CapabilityDescriptor;
}

export function CapabilityBadges({ capability }: CapabilityBadgesProps) {
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      <Badge variant="outline">{SOURCE_TYPE_LABEL[capability.source_type]}</Badge>
      <Badge variant={MUTATION_LEVEL_VARIANT[capability.mutation_level]}>
        {MUTATION_LEVEL_LABEL[capability.mutation_level]}
      </Badge>
      {capability.visibility !== 'normal' && (
        <Badge variant="outline">{VISIBILITY_LABEL[capability.visibility]}</Badge>
      )}
    </div>
  );
}
