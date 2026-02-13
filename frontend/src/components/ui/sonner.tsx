import { Toaster as Sonner } from 'sonner';

type ToasterProps = React.ComponentProps<typeof Sonner>;

const Toaster = ({ ...props }: ToasterProps) => {
  return (
    <Sonner
      theme="system"
      expand
      visibleToasts={5}
      duration={3000}
      className="toaster group"
      position="bottom-right"
      closeButton
      toastOptions={{
        classNames: {
          toast:
            '!rounded-xl !border !bg-card !text-card-foreground !shadow-lg',
          title: '!text-card-foreground !font-semibold',
          description: '!text-muted-foreground',
          actionButton:
            '!bg-primary !text-primary-foreground !rounded-md !hover:!bg-primary/90 !transition-colors',
          cancelButton:
            '!bg-muted !text-muted-foreground !rounded-md !hover:!bg-muted/80 !transition-colors',
          closeButton:
            '!absolute !right-2 !top-2 !left-auto !w-6 !h-6 !min-w-6 !min-h-6 !p-1.5 !bg-transparent !text-muted-foreground !hover:!bg-muted !border-border !flex !items-center !justify-center',
          success:
            '!border-emerald-500/50 !bg-card dark:!bg-card',
          error:
            '!border-destructive/50 !bg-card dark:!bg-card',
          warning:
            '!border-amber-500/50 !bg-card dark:!bg-card',
          info:
            '!border-blue-500/50 !bg-card dark:!bg-card',
        },
      }}
      {...props}
    />
  );
};

export { Toaster };
