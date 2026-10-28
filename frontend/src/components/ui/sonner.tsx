import { Toaster as Sonner } from "sonner"

type ToasterProps = React.ComponentProps<typeof Sonner>

const Toaster = ({ ...props }: ToasterProps) => {
  return (
    <Sonner
      className="toaster group"
      position="bottom-right"
      visibleToasts={5}
      expand
      gap={8}
      duration={3000}
      closeButton
      {...props}
    />
  )
}

export { Toaster }
