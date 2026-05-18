# SimpleJWT adapter

Reference for the optional adapter that plugs
`djangorestframework-simplejwt` into restflow's async dispatch.
See the [SimpleJWT guide](../../guide/authentication/simplejwt.md)
for installation and usage notes.

The class lives at
`restflow.authentication.simplejwt.SimpleJWTAuthentication` and is
not re-exported at the package root because importing it without
the `simplejwt` extra installed raises `ImportError`. Install with
`pip install drf-restflow[simplejwt]`.

::: restflow.authentication.simplejwt.SimpleJWTAuthentication
