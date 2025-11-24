find_package(PkgConfig)

PKG_CHECK_MODULES(PC_GR_SELECTOR gnuradio-selector)

FIND_PATH(
    GR_SELECTOR_INCLUDE_DIRS
    NAMES gnuradio/selector/api.h
    HINTS $ENV{SELECTOR_DIR}/include
        ${PC_SELECTOR_INCLUDEDIR}
    PATHS ${CMAKE_INSTALL_PREFIX}/include
          /usr/local/include
          /usr/include
)

FIND_LIBRARY(
    GR_SELECTOR_LIBRARIES
    NAMES gnuradio-selector
    HINTS $ENV{SELECTOR_DIR}/lib
        ${PC_SELECTOR_LIBDIR}
    PATHS ${CMAKE_INSTALL_PREFIX}/lib
          ${CMAKE_INSTALL_PREFIX}/lib64
          /usr/local/lib
          /usr/local/lib64
          /usr/lib
          /usr/lib64
          )

include("${CMAKE_CURRENT_LIST_DIR}/gnuradio-selectorTarget.cmake")

INCLUDE(FindPackageHandleStandardArgs)
FIND_PACKAGE_HANDLE_STANDARD_ARGS(GR_SELECTOR DEFAULT_MSG GR_SELECTOR_LIBRARIES GR_SELECTOR_INCLUDE_DIRS)
MARK_AS_ADVANCED(GR_SELECTOR_LIBRARIES GR_SELECTOR_INCLUDE_DIRS)
