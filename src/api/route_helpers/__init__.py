"""
Helper functions extracted from `src/api/routes/`. One module per route
file, containing the non-endpoint code that the route delegates to.

Layering: helpers live alongside the API layer (`api/route_helpers`),
not in `domain/` — they're response-shape assemblers and request guards,
not business logic. The strict `api → domain → db` import direction
still holds.
"""
