import { Toaster as Sonner } from "sonner"
import { useViewport } from "@/lib/ui/responsive"

type ToasterProps = React.ComponentProps<typeof Sonner>

/**
 * Toasts sit at the bottom centre of the screen (index.css keeps them clear of an open side panel or sheet).
 * On a phone they move to the top: the bottom edge belongs to the sticky Approve / Reject bar and the sheets.
 */
const Toaster = ({ ...props }: ToasterProps) => {
  const { isPhone } = useViewport()
  return (
    <Sonner
      className="toaster group"
      position={isPhone ? "top-center" : "bottom-center"}
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
