import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { UnifiedLayout } from '../layouts/UnifiedLayout';
import { SkillFormPage } from './SkillFormPage';
import { getSkill } from '../services/skillApi';

export { SkillFormPageWrapper };
export default SkillFormPageWrapper;

function SkillFormPageWrapper() {
  const { id } = useParams<{ id: string }>();
  const [skillTitle, setSkillTitle] = useState<string>('New Skill');
  const isNew = id === 'new';

  useEffect(() => {
    if (id && !isNew) {
      getSkill(id)
        .then((skill) => {
          setSkillTitle(skill.title || skill.skill_name || skill.name);
        })
        .catch((error) => {
          console.error('Error loading skill:', error);
          setSkillTitle('Skill');
        });
    } else {
      setSkillTitle('New Skill');
    }
  }, [id, isNew]);

  const breadcrumbs = [
    { label: 'Skills', href: '/skills' },
    { label: skillTitle },
  ];

  return (
    <UnifiedLayout breadcrumbs={breadcrumbs}>
      <SkillFormPage />
    </UnifiedLayout>
  );
}
