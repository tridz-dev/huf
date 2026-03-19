import { Toaster as Sonner } from "sonner"

type ToasterProps = React.ComponentProps<typeof Sonner>

const Toaster = ({ ...props }: ToasterProps) => {
  return (
    <Sonner
      className="toaster group"
      position="bottom-right"
      visibleToasts={5}
      duration={3000}
      closeButton
      {...props}
    />
  )
}

export { Toaster }
