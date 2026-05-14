"use server";

import { QueryRequest, QueryResponse } from "./types";
import { getInternalToken } from "./auth";

/**
 * Server-side explicit fetch preventing API logic and tokens 
 * from reaching the client boundaries.
 */
export async function executeQuery(req: QueryRequest): Promise<QueryResponse> {
    const token = await getInternalToken();
    const apiUrl = process.env.INTERNAL_API_URL;
    
    const res = await fetch(`${apiUrl}/query/`, {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
            "Authorization": `Bearer ${token}`
        },
        body: JSON.stringify({
            query: req.query,
            domain_tags: req.domain_tags,
            max_sensitivity: req.max_sensitivity || "PUBLIC"
        }),
        cache: 'no-store'
    });

    if (!res.ok) {
        throw new Error("Target downstream rejected query.");
    }

    const data: QueryResponse = await res.json();
    return data;
}
