import { HttpResponse, type RequestOptions, type Transport } from "../dist/http.js";
import { RecordedTransport } from "../dist/testing.js";

export type Rewrite = (method: string, url: string, answer: HttpResponse) => HttpResponse;

/** Replays the recorded answers, passing each through `rewrite` (to fake a shape change). */
export class RewritingTransport implements Transport {
  readonly inner = new RecordedTransport();
  calls = 0;
  constructor(private readonly rewrite: Rewrite) {}

  async request(method: string, url: string, options: RequestOptions = {}): Promise<HttpResponse> {
    this.calls += 1;
    return this.rewrite(method, url, await this.inner.request(method, url, options));
  }
}

/** The same response with a different JSON body. */
export function withJson(response: HttpResponse, data: unknown): HttpResponse {
  return response.with({ content: new TextEncoder().encode(JSON.stringify(data)) });
}

/** A response from a text body. */
export function reply(status: number, body: string | Uint8Array, contentType = "text/plain"): HttpResponse {
  const content = typeof body === "string" ? new TextEncoder().encode(body) : body;
  return new HttpResponse(status, content, contentType, "u");
}

export type Seen = { method: string; url: string; options: RequestOptions };

/** Answers every request with the same response, or throws the given error. */
export class StaticTransport implements Transport {
  readonly requests: Seen[] = [];
  constructor(private readonly answer: HttpResponse | Error) {}

  async request(method: string, url: string, options: RequestOptions = {}): Promise<HttpResponse> {
    this.requests.push({ method, url, options });
    if (this.answer instanceof Error) throw this.answer;
    return this.answer;
  }
}
