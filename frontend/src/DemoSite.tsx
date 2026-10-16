import { useEffect, useState } from "react";
export default function DemoSite({ token }: { token: string }) {
  const [message, setMessage] = useState("");
  useEffect(() => {
    const script = document.createElement("script");
    script.src = "/widget.js";
    script.dataset.project = token;
    document.body.appendChild(script);
    return () => {
      script.remove();
      document.getElementById("bugbrief-launcher")?.remove();
    };
  }, [token]);
  return (
    <div className="embedded-demo">
      <header>
        <span>LITTLE MARKET</span>
        <a href="/">Back to agency workspace ↗</a>
      </header>
      <main>
        <div className="demo-pill">CUSTOMER WORKFLOW PREVIEW</div>
        <h1>
          A small shop.
          <br />A few rough edges.
        </h1>
        <p>
          This is a test website with deliberate defects. Use the floating
          “Report a problem” button to send an issue as a customer.
        </p>
        <div className="demo-product">
          <div className="demo-product-art">✳</div>
          <div>
            <small>EVERYDAY ESSENTIALS</small>
            <h2>The everyday tote</h2>
            <p>A little room for everything.</p>
            <strong>₹499</strong>
            <button>Pay now</button>
            <span className="demo-defect">
              Intentional defect: this button does nothing.
            </span>
          </div>
        </div>
        <section>
          <h2>Keep in touch.</h2>
          <form
            onSubmit={(event) => {
              event.preventDefault();
              event.currentTarget.reset();
              setMessage("Something went wrong. Please try again.");
            }}
          >
            <label>
              Your name
              <input required />
            </label>
            <label>
              Your message
              <input required />
            </label>
            <button>Send message</button>
          </form>
          <p role="status">{message}</p>
          <small>
            Intentional defect: values clear even when submission fails.
          </small>
        </section>
        <section>
          <h2>Delivery details</h2>
          <div className="demo-overlap">
            <span>Your order</span>
            <span>Delivery address</span>
          </div>
          <small>
            Intentional defect: these panels overlap on a narrow screen.
          </small>
        </section>
      </main>
    </div>
  );
}
