"use server";

/**
 * Auth mock boundary explicitly bounded to server runtime.
 * In a true implementation this reads HTTP-only cookies injected by an OAuth/LDAP gateway.
 * The browser never sees this.
 */
export async function getInternalToken(): Promise<string> {
    // DO NOT EXPOSE TO BROWSER
    // Return a mocked JWT token string ensuring the local backend processes it.
    // In Phase 5 scope, API security is established at the Reverse Proxy layer 
    // or through server-side secret injection.
    return "mock.jwt.token.server.bound";
}
