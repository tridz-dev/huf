export const integrationCategories = [
  'Communication',
  'Project Management',
  'Search',
  'Data Sources',
  'Finance',
  'Google',
  'Developer',
  'Cloud',
  'Media',
  'Other',
] as const;

export type IntegrationCategory = (typeof integrationCategories)[number];

export const integrationCategoryFilterOptions = [
  { label: 'All categories', value: 'all' },
  ...integrationCategories.map((category) => ({ label: category, value: category })),
];
