import { Compass } from "lucide-react";
import { Link } from "react-router-dom";
import { EmptyState } from "../components/ui";

export default function NotFound() {
  return (
    <div className="page">
      <div className="card">
        <EmptyState
          icon={Compass}
          title="This page does not exist"
          action={<Link className="btn btn-primary" to="/">Back to requests</Link>}
        >
          The link may be old, or the page was moved.
        </EmptyState>
      </div>
    </div>
  );
}
