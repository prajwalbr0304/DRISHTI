import { useNavigate } from "react-router-dom";
import { Compass } from "lucide-react";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/common/EmptyState";

export function NotFound() {
  const navigate = useNavigate();
  return (
    <EmptyState
      icon={Compass}
      title="Page not found"
      description="That destination doesn't exist. Head back to the Command Center."
      action={
        <Button variant="secondary" onClick={() => navigate("/")}>
          Go to Command Center
        </Button>
      }
    />
  );
}
